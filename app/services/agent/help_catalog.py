"""Small routing catalog; detailed product knowledge is loaded only after selection."""

import json
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


HELP_TOPICS = {
    'notes': ('Notes and editing', 'Hierarchy, editing, moving, copying, undo and keyboard/mouse controls.'),
    'search': ('Search and views', 'Tag/text queries, OR, exclusions, matching, sorting and untagged view.'),
    'tags': ('Tags and ontology', 'Assignment, inheritance, suggestions and tag relationship rules.'),
    'formatting': ('Formatting and attachments', 'Markdown, LaTeX, Mermaid, formatting scopes and files.'),
    'references': ('References and floating notes', 'Links, transclusions, backlinks and floating windows.'),
    'menus': ('Menus and settings', 'Find/open menu dialogs and understand preference controls.'),
    'reminders': ('Reminders', 'Creating, editing, snoozing and recurrence.'),
    'ai': ('AI and tag proposals', 'OpenAI settings, context limits, prompts/skills, tagging and history export.'),
    'privacy': ('Privacy and security', 'Cloud disclosure, gray notes when hovering chat, password exclusion, encryption and credentials.'),
    'data': ('Namespaces and backups', 'Namespaces, backup/restore, HTML export, ports and updates.'),
}
HelpTopic = Literal[tuple(HELP_TOPICS)]
MENU_ACTIONS = json.loads(files('app').joinpath('static/config/agent-menu-actions.json').read_text(encoding='utf-8'))
assert len({entry['id'] for entry in MENU_ACTIONS}) == len(MENU_ACTIONS)
MENU_BY_ID = {entry['id']: entry for entry in MENU_ACTIONS}
MenuId = Literal[('none', *MENU_BY_ID)]


class MetaListHelpResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    answer: str = Field(..., min_length=1, max_length=24000)
    menu_id: MenuId = Field(..., description='One supported menu destination to open, or none. Palette entries are highlighted only; opening never executes them.')

    @field_validator('answer')
    @classmethod
    def reject_blank_answer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Help answer must not be blank')
        return value


HELP_RESPONSE_INSTRUCTION = files('app.services.agent.prompts').joinpath('help-response.md').read_text(encoding='utf-8').rstrip('\n')
