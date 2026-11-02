"""A small Markdown reader.

It is not a full CommonMark implementation. It splits a document into
heading-scoped sections and skips fenced code blocks and HTML comments, which
is enough to keep prose that merely *looks* like a date or a phase heading out
of the evidence set.

Document text is always treated as untrusted data: nothing here executes,
evaluates, or follows instructions found in a document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")


@dataclass
class Section:
    level: int
    heading: str
    path: List[str]
    lines: List[tuple] = field(default_factory=list)  # (line number, raw text)


@dataclass
class Document:
    relative_path: str
    title: str
    sections: List[Section]


def parse_document(relative_path: str, text: str) -> Document:
    sections: List[Section] = []
    stack: List[str] = []
    current = Section(level=0, heading="", path=[], lines=[])
    title = ""

    in_fence = False
    fence_token = ""
    in_comment = False

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()

        fence = FENCE_RE.match(line)
        if fence:
            token = fence.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_token = token
                continue
            if token == fence_token:
                in_fence = False
                continue
        if in_fence:
            continue

        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if "<!--" in line:
            if "-->" not in line.split("<!--", 1)[1]:
                in_comment = True
            continue

        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            text_heading = heading.group(2).strip()
            if level == 1 and not title:
                title = text_heading
            sections.append(current)
            while len(stack) >= level:
                stack.pop()
            stack.append(text_heading)
            current = Section(level=level, heading=text_heading, path=list(stack), lines=[])
            continue

        current.lines.append((number, line))

    sections.append(current)
    return Document(relative_path=relative_path, title=title, sections=[s for s in sections if s.heading or s.lines])


def section_block(sections: List[Section], index: int) -> List[tuple]:
    """Lines belonging to a section plus all nested subsections."""
    lines: List[tuple] = list(sections[index].lines)
    level = sections[index].level
    for following in sections[index + 1:]:
        if following.heading and following.level <= level:
            break
        lines.extend(following.lines)
    return lines


def find_section(sections: List[Section], keywords) -> Optional[Section]:
    lowered = [keyword.lower() for keyword in keywords]
    for section in sections:
        if not section.heading:
            continue
        heading = section.heading.lower()
        if any(keyword in heading for keyword in lowered):
            return section
    return None
