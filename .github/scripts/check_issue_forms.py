#!/usr/bin/env python3
"""Check the issue forms and config.yml in .github/ISSUE_TEMPLATE.

GitHub shows an issue form's validation errors when someone creates, saves, or
views the form on GitHub. This script finds them on each pull request instead,
checking every form, and config.yml, against the syntax in GitHub's
documentation: "Syntax for issue forms", "Syntax for GitHub's form schema",
"Common validation errors when creating issue forms", and "Configuring issue
templates for your repository". It adds one Kingfish rule: every form sets an
issue type that CONTRIBUTING.md names.

Run it from the repository root:

    uv run --with 'pyyaml==6.0.3' .github/scripts/check_issue_forms.py [DIRECTORY]

DIRECTORY defaults to .github/ISSUE_TEMPLATE. The script prints one line per
problem and exits 1 when it finds any.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

# The issue types CONTRIBUTING.md names. Every form sets one, spelled exactly.
ISSUE_TYPES = ("Task", "Bug", "Feature")

# YAML reads these words as booleans, and GitHub forbids them as keys.
FORBIDDEN_KEYS = frozenset(
    {
        *("y", "Y", "yes", "Yes", "YES", "n", "N", "no", "No", "NO"),
        *("true", "True", "TRUE", "false", "False", "FALSE"),
        *("on", "On", "ON", "off", "Off", "OFF"),
    }
)

ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+")
PROJECT_PATTERN = re.compile(r"[A-Za-z0-9-]+/[0-9]+")

# A spec maps each permitted key to (kind, required). The kinds:
#   string   a string with something besides whitespace in it
#   strings  one such string (comma-delimited) or a non-empty list of them
#   list     a list
#   mapping  a mapping
#   boolean  true or false
#   count    a whole number, 0 or more
Spec = dict[str, tuple[str, bool]]

FORM: Spec = {
    "name": ("string", True),
    "description": ("string", True),
    "body": ("list", True),
    "assignees": ("strings", False),
    "labels": ("strings", False),
    "title": ("string", False),
    "type": ("string", False),  # Optional for GitHub; check_form requires it.
    "projects": ("strings", False),
}

ELEMENT: Spec = {
    "type": ("string", True),
    "id": ("string", False),
    "attributes": ("mapping", True),
    "validations": ("mapping", False),
}

_LABEL = ("string", True)
_TEXT = ("string", False)
_REQUIRED: Spec = {"required": ("boolean", False)}

# The attributes, then the validations, that each element type takes.
ELEMENTS: dict[str, tuple[Spec, Spec]] = {
    "markdown": ({"value": ("string", True)}, {}),
    "textarea": (
        {
            "label": _LABEL,
            "description": _TEXT,
            "placeholder": _TEXT,
            "value": _TEXT,
            "render": _TEXT,
        },
        {**_REQUIRED, "min_length": ("count", False)},
    ),
    "input": (
        {
            "label": _LABEL,
            "description": _TEXT,
            "placeholder": _TEXT,
            "value": _TEXT,
        },
        {**_REQUIRED, "min_length": ("count", False)},
    ),
    "dropdown": (
        {
            "label": _LABEL,
            "description": _TEXT,
            "multiple": ("boolean", False),
            "options": ("list", True),
            "default": ("count", False),
        },
        _REQUIRED,
    ),
    "checkboxes": (
        {"label": _LABEL, "description": _TEXT, "options": ("list", True)},
        _REQUIRED,
    ),
    "upload": (
        {"label": _LABEL, "description": _TEXT},
        {**_REQUIRED, "accept": _TEXT},
    ),
}

CHECKBOX_OPTION: Spec = {"label": ("string", True), "required": ("boolean", False)}

CONFIG: Spec = {
    "blank_issues_enabled": ("boolean", False),
    "contact_links": ("list", False),
}

# GitHub's example contact link sets all three.
CONTACT_LINK: Spec = {
    "name": ("string", True),
    "url": ("string", True),
    "about": ("string", True),
}

SHORT_NAME = (
    "GitHub leaves a template out of the chooser unless its name is longer "
    "than 3 characters."
)


class Mapping(dict[Any, Any]):
    """A YAML mapping that remembers the line of each key."""

    lines: dict[Any, int]


class Sequence(list[Any]):
    """A YAML sequence that remembers the line of each item."""

    lines: list[int]


class Loader(yaml.SafeLoader):
    """A SafeLoader that records line numbers and notes repeated keys."""

    repeated: list[tuple[int, Any]]
    cut_short: list[tuple[int, str]]


def _note_cut_short(loader: Loader, node: yaml.Node) -> None:
    # A plain scalar ends where " #" starts a YAML comment, so "such as #12."
    # loses "#12." without any error. Note values followed by "#" and a
    # non-space character, which reads as a number or a heading, not a comment.
    if isinstance(node, yaml.ScalarNode) and node.style is None:
        mark = node.end_mark
        rest = (mark.buffer or "")[mark.pointer :].split("\n", 1)[0]
        if re.match(r"[ \t]+#\S", rest):
            loader.cut_short.append((mark.line + 1, node.value))


def _construct_mapping(loader: Loader, node: yaml.MappingNode) -> Mapping:
    # PyYAML keeps the last of two equal keys without a word, which would hide
    # a mistake such as a second "validations:" under one element.
    seen: set[Any] = set()
    for _, value_node in node.value:
        _note_cut_short(loader, value_node)
    for key_node, _ in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            continue
        key = loader.construct_object(key_node, deep=True)
        with contextlib.suppress(TypeError):  # SafeLoader reports unhashable keys.
            if key in seen:
                loader.repeated.append((key_node.start_mark.line + 1, key))
            seen.add(key)
    data = Mapping(loader.construct_mapping(node, deep=True))
    data.lines = {}
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=True)
        with contextlib.suppress(TypeError):
            data.lines.setdefault(key, key_node.start_mark.line + 1)
    return data


def _construct_sequence(loader: Loader, node: yaml.SequenceNode) -> Sequence:
    for child in node.value:
        _note_cut_short(loader, child)
    data = Sequence(loader.construct_object(child, deep=True) for child in node.value)
    data.lines = [child.start_mark.line + 1 for child in node.value]
    return data


Loader.add_constructor("tag:yaml.org,2002:map", _construct_mapping)
Loader.add_constructor("tag:yaml.org,2002:seq", _construct_sequence)


def _line_of(container: Any, key: Any, default: int) -> int:
    """Return the line of a key or item, or default when it is unknown."""
    lines = getattr(container, "lines", None)
    if isinstance(lines, dict):
        try:
            return int(lines.get(key, default))
        except TypeError:
            return default
    if isinstance(lines, list) and isinstance(key, int) and 0 <= key < len(lines):
        return int(lines[key])
    return default


def _where(parent: str, key: Any) -> str:
    """Name a key or list index the way GitHub's errors do, as in body[2].id."""
    if isinstance(key, int) and not isinstance(key, bool):
        return f"{parent}[{key}]"
    return f"{parent}.{key}" if parent else str(key)


def _quote(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def _describe(value: Any) -> str:
    """Name what YAML made of a value, for an error message."""
    if value is None:
        return "empty"
    if isinstance(value, bool):
        return f"the boolean {str(value).lower()}"
    if isinstance(value, (int, float)):
        return f"the number {value}"
    if isinstance(value, dict):
        return "a mapping"
    if isinstance(value, list):
        return "a list"
    return f"the string {_quote(str(value))}"


def _reference(label: str) -> str:
    """Turn a label into the field reference GitHub derives from it.

    GitHub uses Rails' parameterize. For ASCII labels this matches it: each
    run of characters other than letters, digits, - and _ becomes one -, with
    no - at either end, all lowercase. For other characters it is close but
    not exact: Rails transliterates with I18n's table (so a sharp s becomes
    ss) and turns a character it cannot map into -, while this drops accents
    and any character that does not decompose to ASCII. Two non-ASCII labels
    can therefore clash on GitHub and pass here, or the reverse, so keep
    labels ASCII.
    """
    text = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9_-]+", "-", text, flags=re.IGNORECASE)
    return re.sub(r"-{2,}", "-", text).strip("-").lower()


def _strings(value: Any) -> list[str]:
    """Return the entries of a list or of a comma-delimited string."""
    if isinstance(value, str):
        return [part.strip() for part in value.split(",")]
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str)]
    return []


@dataclass
class Checker:
    """Collects the problems found in one file."""

    path: Path
    problems: list[tuple[int, str]] = field(default_factory=list)

    def report(self, line: int, message: str) -> None:
        """Record one problem at a line of the file."""
        self.problems.append((line, message))

    def check_kind(self, value: Any, kind: str, where: str, line: int) -> bool:
        """Report a value of the wrong kind, and return whether it was right."""
        if kind == "string":
            if not isinstance(value, str):
                self.report(line, f"{where} must be a string, not {_describe(value)}")
                return False
            if not value.strip():
                self.report(line, f"{where} must not be empty or only whitespace")
                return False
            return True
        if kind == "strings":
            if not isinstance(value, list):
                return self.check_kind(value, "string", where, line)
            if not value:
                self.report(line, f"{where} must not be an empty list")
                return False
            results = [
                self.check_kind(
                    item, "string", _where(where, index), _line_of(value, index, line)
                )
                for index, item in enumerate(value)
            ]
            return all(results)
        if kind == "list":
            ok, expected = isinstance(value, list), "a list"
        elif kind == "mapping":
            ok, expected = isinstance(value, dict), "a mapping"
        elif kind == "boolean":
            ok, expected = isinstance(value, bool), "true or false"
        elif kind == "count":
            ok = isinstance(value, int) and not isinstance(value, bool) and value >= 0
            expected = "a whole number, 0 or more"
        else:
            raise ValueError(f"unknown kind {kind}")
        if not ok:
            self.report(line, f"{where} must be {expected}, not {_describe(value)}")
        return ok

    def check_mapping(self, data: Any, spec: Spec, where: str, line: int) -> bool:
        """Check a mapping's keys and the kind of each value in it.

        Returns False when data is not a mapping at all, so that the caller
        can skip the checks that depend on its contents.
        """
        place = where or "The file"
        if not isinstance(data, dict):
            self.report(line, f"{place} must be a mapping, not {_describe(data)}")
            return False
        for key in data:
            key_line = _line_of(data, key, line)
            if not isinstance(key, str):
                self.report(
                    key_line,
                    f"{place} has a key that YAML reads as {_describe(key)}. GitHub "
                    "forbids yes, no, on, off, true, false, y, and n as keys.",
                )
            elif key in FORBIDDEN_KEYS:
                self.report(key_line, f"{_where(where, key)}: GitHub forbids this key")
            elif key not in spec:
                self.report(key_line, f"{_where(where, key)} is not a permitted key")
        for key, (kind, required) in spec.items():
            key_where = _where(where, key)
            if key in data:
                self.check_kind(data[key], kind, key_where, _line_of(data, key, line))
            elif required:
                self.report(line, f"{key_where} is required and missing")
        return True


def check_form(checker: Checker, data: Any) -> tuple[str, int] | None:
    """Check one issue form, and return its name and line if it has one."""
    if not checker.check_mapping(data, FORM, "", 1):
        return None

    name = data.get("name")
    name_line = _line_of(data, "name", 1)
    has_name = isinstance(name, str) and bool(name.strip())
    if has_name and len(name.strip()) <= 3:
        checker.report(
            name_line,
            f"name {_quote(name)} has {len(name.strip())} characters. {SHORT_NAME}",
        )

    issue_type = data.get("type")
    choices = ", ".join(ISSUE_TYPES)
    if "type" not in data:
        checker.report(
            1, f"type is missing. Every Kingfish form sets one of {choices}."
        )
    elif (
        isinstance(issue_type, str)
        and issue_type.strip()
        and issue_type not in ISSUE_TYPES
    ):
        checker.report(
            _line_of(data, "type", 1),
            f"type {_quote(issue_type)} is not one of the issue types "
            f"CONTRIBUTING.md names: {choices}",
        )

    for project in _strings(data.get("projects")):
        if project and not PROJECT_PATTERN.fullmatch(project):
            checker.report(
                _line_of(data, "projects", 1),
                f"projects: {_quote(project)} is not in the form OWNER/NUMBER, "
                "such as KingfishProject/5",
            )

    body = data.get("body")
    if isinstance(body, list):
        check_body(checker, body, _line_of(data, "body", 1))

    return (name.strip(), name_line) if has_name else None


def check_body(checker: Checker, body: list[Any], line: int) -> None:
    """Check the elements of a form's body, and the ids and labels across them."""
    if not body:
        checker.report(line, "body must not be empty")
        return

    # Each input element is known by its id, or else by a reference GitHub
    # builds from its label. Two elements with one reference collide.
    references: dict[str, tuple[str, str]] = {}
    option_references: list[tuple[str, str, int, str]] = []
    has_input = False

    for index, element in enumerate(body):
        where = f"body[{index}]"
        element_line = _line_of(body, index, line)
        if not checker.check_mapping(element, ELEMENT, where, element_line):
            continue
        element_type = element.get("type")
        if not isinstance(element_type, str) or not element_type.strip():
            continue
        if element_type not in ELEMENTS:
            checker.report(
                _line_of(element, "type", element_line),
                f"{where}.type {_quote(element_type)} is not a valid input type. "
                f"Use one of: {', '.join(ELEMENTS)}.",
            )
            continue

        attribute_spec, validation_spec = ELEMENTS[element_type]
        attributes = element.get("attributes")
        attributes_line = _line_of(element, "attributes", element_line)
        if isinstance(attributes, dict):
            checker.check_mapping(
                attributes, attribute_spec, f"{where}.attributes", attributes_line
            )
        else:
            attributes = {}
        validations = element.get("validations")
        if isinstance(validations, dict):
            checker.check_mapping(
                validations,
                validation_spec,
                f"{where}.validations",
                _line_of(element, "validations", element_line),
            )

        element_id = element.get("id")
        id_line = _line_of(element, "id", element_line)
        if element_type == "markdown":
            if "id" in element:
                checker.report(id_line, f"{where}.id: a markdown element takes no id")
            continue
        has_input = True

        reference, source = None, ""
        if isinstance(element_id, str) and element_id.strip():
            if not ID_PATTERN.fullmatch(element_id):
                checker.report(
                    id_line,
                    f"{where}.id {_quote(element_id)} can only contain letters, "
                    "digits, -, and _",
                )
            reference, source = element_id, "id"
        label = attributes.get("label")
        if reference is None and isinstance(label, str) and label.strip():
            reference, source = _reference(label), "label"
        if reference is not None:
            if reference in references:
                other, other_source = references[reference]
                if source == other_source == "id":
                    checker.report(
                        id_line,
                        f"{where}.id {_quote(reference)} is already the id of "
                        f"{other}. Ids must be unique.",
                    )
                else:
                    checker.report(
                        element_line,
                        f"{where} and {other} share the field reference "
                        f"{_quote(reference)}, from their ids or labels. Give one "
                        "of them a unique id or a different label.",
                    )
            else:
                references[reference] = (where, source)

        # GitHub rejects some words in these labels and names only "password".
        if (
            element_type in ("input", "textarea")
            and isinstance(label, str)
            and "password" in label.lower()
        ):
            checker.report(
                _line_of(attributes, "label", attributes_line),
                f"{where}.attributes.label: GitHub forbids the word password here",
            )

        options = attributes.get("options")
        options_line = _line_of(attributes, "options", attributes_line)
        if element_type not in ("dropdown", "checkboxes"):
            continue
        if not isinstance(options, list):
            continue
        if not options:
            checker.report(options_line, f"{where}.attributes.options is empty")
        elif element_type == "dropdown":
            check_dropdown(checker, attributes, options, where, options_line)
        else:
            for found in check_checkboxes(checker, options, where, options_line):
                option_references.append((*found, where))

    # A checkbox's label must also differ from the other elements' references.
    for reference, option_where, option_line, owner in option_references:
        other = references.get(reference, (owner, ""))[0]
        if other != owner:
            checker.report(
                option_line,
                f"{option_where}.label shares the field reference {_quote(reference)} "
                f"with {other}. Change the label, or give {other} a unique id.",
            )

    if not has_input:
        checker.report(line, "body needs at least one element that is not markdown")


def check_dropdown(
    checker: Checker,
    attributes: dict[str, Any],
    options: list[Any],
    where: str,
    line: int,
) -> None:
    """Check a dropdown's options and its default."""
    seen: dict[str, int] = {}
    for index, option in enumerate(options):
        option_where = f"{where}.attributes.options[{index}]"
        option_line = _line_of(options, index, line)
        if not isinstance(option, str):
            checker.report(
                option_line,
                f"{option_where} must be a string, not {_describe(option)}. "
                "Quote values such as yes and true.",
            )
            continue
        if not option.strip():
            checker.report(option_line, f"{option_where} must not be empty")
            continue
        if option in seen:
            checker.report(
                option_line, f"{option_where} repeats options[{seen[option]}]"
            )
        else:
            seen[option] = index
        word = option.strip().lower()
        if word == "none":
            checker.report(
                option_line,
                f"{option_where}: None is reserved. GitHub adds it to a dropdown "
                "that is not required.",
            )
        elif word == "n/a" and "default" in attributes:
            checker.report(
                option_line,
                f"{option_where}: a dropdown with a default cannot offer n/a",
            )

    default = attributes.get("default")
    if (
        isinstance(default, int)
        and not isinstance(default, bool)
        and default >= len(options)
    ):
        checker.report(
            _line_of(attributes, "default", line),
            f"{where}.attributes.default is {default}, but the last option is "
            f"options[{len(options) - 1}]",
        )


def check_checkboxes(
    checker: Checker, options: list[Any], where: str, line: int
) -> list[tuple[str, str, int]]:
    """Check a checkboxes element's options, and return their field references."""
    found: list[tuple[str, str, int]] = []
    seen: dict[str, str] = {}
    for index, option in enumerate(options):
        option_where = f"{where}.attributes.options[{index}]"
        option_line = _line_of(options, index, line)
        if not checker.check_mapping(
            option, CHECKBOX_OPTION, option_where, option_line
        ):
            continue
        label = option.get("label")
        if not isinstance(label, str) or not label.strip():
            continue
        reference = _reference(label)
        label_line = _line_of(option, "label", option_line)
        if reference in seen:
            checker.report(
                label_line,
                f"{option_where}.label is too close to {seen[reference]}.label. "
                "Each checkbox needs a distinct label.",
            )
        else:
            seen[reference] = option_where
        found.append((reference, option_where, label_line))
    return found


def check_config(checker: Checker, data: Any) -> None:
    """Check config.yml, the template chooser's settings."""
    if data is None:
        return  # An empty config.yml changes nothing.
    if not checker.check_mapping(data, CONFIG, "", 1):
        return
    links = data.get("contact_links")
    if not isinstance(links, list):
        return
    links_line = _line_of(data, "contact_links", 1)
    for index, link in enumerate(links):
        where = f"contact_links[{index}]"
        link_line = _line_of(links, index, links_line)
        if not checker.check_mapping(link, CONTACT_LINK, where, link_line):
            continue
        url = link.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        parts = urlsplit(url.strip())
        if parts.scheme not in ("http", "https") or not parts.netloc:
            checker.report(
                _line_of(link, "url", link_line),
                f"{where}.url {_quote(url)} must be a full http or https URL, such "
                "as https://kingfish.la/",
            )


def check_markdown_template(checker: Checker) -> tuple[str, int] | None:
    """Return a Markdown template's name, for the check that names are unique."""
    try:
        lines = checker.path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        checker.report(1, "the file is not UTF-8 text")
        return None
    if not lines or lines[0].strip() != "---":
        return None
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        checker.report(1, "the front matter has no closing ---")
        return None
    try:
        front = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as error:
        problem = getattr(error, "problem", None) or error
        checker.report(1, f"the front matter is not valid YAML: {problem}")
        return None
    name = front.get("name") if isinstance(front, dict) else None
    if not isinstance(name, str) or not name.strip():
        return None
    name_line = next(
        (i + 1 for i, text in enumerate(lines[:end]) if text.startswith("name:")), 1
    )
    if len(name.strip()) <= 3:
        checker.report(
            name_line,
            f"name {_quote(name)} has {len(name.strip())} characters. {SHORT_NAME}",
        )
    return name.strip(), name_line


_UNREADABLE = object()


def load(checker: Checker) -> Any:
    """Parse a YAML file, reporting a parse error as a problem."""
    try:
        text = checker.path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        checker.report(1, "the file is not UTF-8 text")
        return _UNREADABLE
    loader = Loader(text)
    loader.repeated = []
    loader.cut_short = []
    try:
        data = loader.get_single_data()
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        line = mark.line + 1 if mark is not None else 1
        problem = getattr(error, "problem", None) or error
        checker.report(line, f"the file is not valid YAML: {problem}")
        return _UNREADABLE
    finally:
        loader.dispose()
    for line, key in loader.repeated:
        checker.report(line, f"the key {key} appears twice in one mapping. Keep one.")
    for line, value in loader.cut_short:
        checker.report(
            line,
            f"the value {_quote(value)} stops where a # starts a YAML comment. "
            "Quote the whole string if the # belongs to it.",
        )
    return data


def _escape(text: str, prop: bool = False) -> str:
    """Escape text for a GitHub Actions workflow command, as @actions/core does."""
    text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    if prop:
        text = text.replace(":", "%3A").replace(",", "%2C")
    return text


def emit(path: Path, line: int, message: str) -> None:
    """Print one problem, as an error annotation when running in GitHub Actions."""
    text = f"{path}:{line}: {message}"
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(
            f"::error file={_escape(str(path), prop=True)},line={line}::{_escape(text)}"
        )
    else:
        print(text)


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def main(argv: list[str]) -> int:
    """Check the directory named on the command line, or the default one."""
    if len(argv) > 2 or (len(argv) == 2 and argv[1].startswith("-")):
        print(f"usage: {Path(argv[0]).name} [DIRECTORY]", file=sys.stderr)
        return 2
    directory = Path(argv[1] if len(argv) == 2 else ".github/ISSUE_TEMPLATE")
    if not directory.is_dir():
        print(f"{directory} is not a directory.", file=sys.stderr)
        return 1

    paths = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix in (".yml", ".yaml", ".md")
    )
    if not any(path.suffix in (".yml", ".yaml") for path in paths):
        print(f"{directory} holds no issue forms.", file=sys.stderr)
        return 1

    checkers: list[Checker] = []
    names: dict[str, Path] = {}
    for path in paths:
        checker = Checker(path)
        checkers.append(checker)
        if path.suffix == ".md":
            found = check_markdown_template(checker)
        elif path.name == "config.yaml":
            checker.report(
                1, "GitHub reads the chooser's settings from config.yml only"
            )
            continue
        else:
            data = load(checker)
            if data is _UNREADABLE:
                continue
            if path.name == "config.yml":
                check_config(checker, data)
                continue
            found = check_form(checker, data)
        if found is None:
            continue
        name, name_line = found
        if name in names:
            checker.report(
                name_line, f"name {_quote(name)} is also the name of {names[name]}"
            )
        else:
            names[name] = path

    count = 0
    for checker in checkers:
        for line, message in sorted(checker.problems, key=lambda problem: problem[0]):
            emit(checker.path, line, message)
            count += 1
    checked = _count(len(checkers), "file")
    if count:
        failing = sum(1 for checker in checkers if checker.problems)
        print(f"{_count(count, 'problem')} in {failing} of {checked} in {directory}.")
        return 1
    print(f"Checked {checked} in {directory}: no problems.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
