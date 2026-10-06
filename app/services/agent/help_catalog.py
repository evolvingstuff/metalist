"""Help topics and the menu catalog; detailed product knowledge lives in the help skills."""

import json
from importlib.resources import files
from typing import Literal


HELP_TOPICS = {
    'notes': ('Notes and editing', 'Hierarchy, editing, moving, copying, undo and keyboard/mouse controls.'),
    'search': ('Search and views', 'Tag/text queries, OR, exclusions, matching, sorting and untagged view.'),
    'tags': ('Tags and ontology', 'Manual tag assignment, inheritance, autocomplete, ontology and tag relationship rules. AI proposal workflows belong to ai.'),
    'formatting': ('Formatting and attachments', 'Markdown, LaTeX, Mermaid, formatting scopes and files.'),
    'references': ('References and floating notes', 'Links, transclusions, backlinks, floating windows and Excalidraw diagrams.'),
    'menus': ('Menus and settings', 'Find/open menu dialogs and understand preference controls.'),
    'reminders': ('Reminders', 'Creating, editing, snoozing and recurrence.'),
    'ai': ('AI and tag proposals', 'OpenAI settings, context limits, prompts/skills, history export, and AI tag proposals: generation, acceptance, rejection/removal and bulk undo limits. This topic alone covers proposal workflow explanations.'),
    'privacy': ('Privacy and security', 'Cloud disclosure, gray notes when hovering chat, password exclusion, encryption and credentials.'),
    'data': ('Namespaces and backups', 'Namespaces, backup/restore, HTML export, ports and updates.'),
    'releases': ('Release notes', 'What changed in each MetaList version (what is new, when a feature or fix arrived).'),
}
HelpTopic = Literal[tuple(HELP_TOPICS)]
MENU_ACTIONS = json.loads(files('app').joinpath('static/config/agent-menu-actions.json').read_text(encoding='utf-8'))
assert len({entry['id'] for entry in MENU_ACTIONS}) == len(MENU_ACTIONS)
MENU_BY_ID = {entry['id']: entry for entry in MENU_ACTIONS}
