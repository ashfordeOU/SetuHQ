# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The command line's help in the user's language (setuhq.i18n).

Every help text of ``setuhq`` (each subcommand's line, each option's help, each description) is a message of the
catalogue, with an id from its place in the parser: ``cli.cmd.<command>`` for a subcommand's line,
``cli.opt.<command>.<option>`` for an option, ``cli.desc.<command>`` for a description. ``tools/i18n.py extract``
reads them from the parser itself (:func:`messages`), so the code stays the one source of the English. argparse's own
words ("usage:", "options", its error lines) are messages too (``cli.argparse.*``). Option names, metavariables and
choices never change: only the words a person reads.
"""

from __future__ import annotations

import argparse
import re

from setuhq import i18n

# argparse's own words (Python 3.11 to 3.13), as its gettext calls name them.
ARGPARSE = {
    "usage: ": "usage",
    "positional arguments": "positional",
    "options": "options",
    "show this help message and exit": "help",
    "show program's version number and exit": "version",
    "%(prog)s: error: %(message)s\n": "error",
    "the following arguments are required: %s": "required",
    "unrecognized arguments: %s": "unrecognized",
    "invalid choice: %(value)r (choose from %(choices)s)": "choice",
    "argument %(argument_name)s: %(message)s": "argument",
    "expected one argument": "one",
}


def _opt_id(action: argparse.Action) -> str:
    name = max(action.option_strings, key=len) if action.option_strings else action.dest
    return re.sub(r"[^\w-]", "", name.lstrip("-")) or action.dest


def _walk(parser: argparse.ArgumentParser, path: str):
    """(id, owner, attribute, English) for every help text of ``parser`` and its subcommands."""
    if parser.description:
        yield f"cli.desc.{path}", parser, "description", parser.description
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for choice in action._choices_actions:
                if choice.help and choice.help != argparse.SUPPRESS:
                    yield f"cli.cmd.{choice.dest}", choice, "help", choice.help
            for name, sub in action.choices.items():
                name = "site" if name == "app" else name  # 'setuhq app' is the old name of 'setuhq site': the same help
                yield from _walk(sub, name if path == "setuhq" else f"{path}.{name}")
            continue
        if action.help and action.help != argparse.SUPPRESS and not isinstance(action, (argparse._HelpAction, argparse._VersionAction)):
            yield f"cli.opt.{path}.{_opt_id(action)}", action, "help", action.help


def _icu(text: str) -> str:
    """Help text as an ICU message: braces quoted (a help that shows a JSON shape or a set)."""
    return re.sub(r"[{}]", lambda m: "'" + m.group(0) + "'", text)


def messages() -> dict[str, str]:
    """Every help text of ``setuhq`` (English, as an ICU message) by id; and argparse's own words."""
    from setuhq.cli import build_parser

    out = {}
    for mid, _, _, en in _walk(build_parser(), "setuhq"):
        out[mid] = _icu(en)
    for en, key in ARGPARSE.items():
        out[f"cli.argparse.{key}"] = en
    return out


def localize_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """``parser`` with its help texts in the current language (each that has a translation)."""
    import gettext

    lang = i18n.current()
    if lang == i18n.SOURCE:
        argparse._ = gettext.gettext
        return parser
    cat = i18n.messages(lang)
    for mid, owner, attr, _ in list(_walk(parser, "setuhq")):
        if cat.get(mid):
            setattr(owner, attr, i18n.format_message(cat[mid], {}, lang))
    words = {en: cat.get(f"cli.argparse.{key}") for en, key in ARGPARSE.items()}
    argparse._ = lambda s: words.get(s) or s  # argparse looks its words up through gettext's _
    return parser
