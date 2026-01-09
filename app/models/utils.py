import html
import re
from typing import Any, Dict, Optional
from types import SimpleNamespace
import uuid
from datetime import datetime, timezone

from ..utils.encryption import encrypt
from ..services.content_cache import (
    get_cached_content,
    get_cached_tags,
    cache_note,
    cache_note_tags,
)
from ..services.note_store import store as note_store
from app.presentation.render.note_renderer import render_read_only_mode
from app.db.notes_sql import (
    fetch_children_ordered,
    fetch_note,
    insert_note,
    update_links,
)
from app.models.database import SafeSession


def copy_note_in_memory(db: SafeSession, note_id: str) -> Dict[str, Any]:
    """
    Serializes a note and all its descendants to a pure data structure.
    
    Args:
        db: Database session
        note_id: ID of the note to serialize
        
    Returns:
        Dictionary representation of the note tree (no database writes)
    """
    # Get the original note
    with SafeSession.allow_reads("copy_note_in_memory:source"):
        source_row = fetch_note(db.connection(), note_id)
    if not source_row:
        raise ValueError(f"Source note with ID {note_id} not found")
    source_note = SimpleNamespace(**source_row)
    
    return _serialize_note_recursive(db, source_note)


def _serialize_note_recursive(db: SafeSession, source_note: Any) -> Dict[str, Any]:
    """
    Recursively serializes a note and all its descendants to pure data.
    
    Args:
        db: Database session
        source_note: The source note to serialize
        
    Returns:
        Dictionary representation of the note and its children
    """
    # Get decrypted content from cache - MUST be there
    decrypted_content = get_cached_content(source_note.id)
    decrypted_tags = get_cached_tags(source_note.id)
    
    # Serialize this note's data
    note_data = {
        "content": decrypted_content,  # Use decrypted content from cache
        "tags": decrypted_tags,
        "created_at": source_note.created_at.isoformat() if source_note.created_at else None,
        "updated_at": source_note.updated_at.isoformat() if source_note.updated_at else None,
        "children": []
    }
    
    # Get all children of the source note in order
    from .linked_list import LinkedListManager
    ordered_children = LinkedListManager.get_ordered_child_list(db, source_note.id)
    
    # Serialize each child recursively
    for child in ordered_children:
        child_data = _serialize_note_recursive(db, child)
        note_data["children"].append(child_data)
    
    return note_data


def paste_note_from_memory(db: SafeSession, note_data: Dict[str, Any], new_parent_id: Optional[str]) -> str:
    """
    Deserializes clipboard data into real database notes with new UUIDs.
    
    Args:
        db: Database session
        note_data: Serialized note data from clipboard
        new_parent_id: Optional parent ID for the pasted note
        
    Returns:
        ID of the new pasted root note
    """
    return _deserialize_note_recursive(db, note_data, new_parent_id)


def _deserialize_note_recursive(db: SafeSession, note_data: Dict[str, Any], new_parent_id: Optional[str]) -> str:
    """
    Recursively deserializes note data into real database notes.
    
    Args:
        db: Database session
        note_data: Serialized note data
        new_parent_id: Optional parent ID for the new note
        
    Returns:
        ID of the new note
    """
    # Generate a new ID for the note and encrypt its content
    new_id = str(uuid.uuid4())
    ciphertext, nonce, tag = encrypt(note_data["content"], "")
    tags_value = note_data["tags"]
    tags_ciphertext, tags_nonce, tags_tag = encrypt(tags_value, "")
    timestamp = datetime.now(timezone.utc)
    is_collapsed = bool(note_data["is_collapsed"])

    insert_note(
        db.connection(),
        note_id=new_id,
        content=ciphertext,
        encryption_nonce=nonce,
        encryption_tag=tag,
        tags=tags_ciphertext,
        tags_encryption_nonce=tags_nonce,
        tags_encryption_tag=tags_tag,
        parent_id=new_parent_id,
        prev_id=None,
        next_id=None,
        is_collapsed=is_collapsed,
        created_at=timestamp,
        updated_at=timestamp,
    )

    cache_note(new_id, note_data["content"])
    cache_note_tags(new_id, tags_value)

    if note_store.loaded:
        note_store.add_note_from_db(
            SimpleNamespace(
                id=new_id,
                content=ciphertext,
                encryption_nonce=nonce,
                encryption_tag=tag,
                tags=tags_ciphertext,
                tags_encryption_nonce=tags_nonce,
                tags_encryption_tag=tags_tag,
                parent_id=new_parent_id,
                prev_id=None,
                next_id=None,
                is_collapsed=is_collapsed,
                created_at=timestamp,
                updated_at=timestamp,
            ),
            note_data["content"],
            tags_value,
        )
    
    # Deserialize children if any
    children_data = note_data["children"]
    if children_data:
        # Deserialize each child recursively
        previous_child_id = None
        for child_data in children_data:
            # Deserialize the child with the new parent ID
            new_child_id = _deserialize_note_recursive(db, child_data, new_id)
            
            # Update prev_id and next_id to maintain sibling order
            if previous_child_id:
                updated_at = datetime.now(timezone.utc)
                update_links(
                    db.connection(),
                    new_child_id,
                    prev_id=previous_child_id,
                    updated_at=updated_at,
                )
                update_links(
                    db.connection(),
                    previous_child_id,
                    next_id=new_child_id,
                    updated_at=updated_at,
                )
                if note_store.loaded:
                    new_child_record = note_store.get_note(new_child_id)
                    prev_record = note_store.get_note(previous_child_id)
                    note_store.update_metadata_from_db(
                        SimpleNamespace(
                            id=new_child_record.id,
                            parent_id=new_child_record.parent_id,
                            prev_id=previous_child_id,
                            next_id=new_child_record.next_id,
                            created_at=new_child_record.created_at,
                            updated_at=new_child_record.updated_at,
                            is_collapsed=new_child_record.is_collapsed,
                        ),
                        rebuild=True,
                    )
                    note_store.update_metadata_from_db(
                        SimpleNamespace(
                            id=prev_record.id,
                            parent_id=prev_record.parent_id,
                            prev_id=prev_record.prev_id,
                            next_id=new_child_id,
                            created_at=prev_record.created_at,
                            updated_at=prev_record.updated_at,
                            is_collapsed=prev_record.is_collapsed,
                        ),
                        rebuild=True,
                    )
            
            previous_child_id = new_child_id
    
    return new_id


def copy_note(db: SafeSession, note_id: str, new_parent_id: Optional[str]) -> str:
    """Create a deep copy of ``note_id`` and its descendants."""

    with SafeSession.allow_reads("copy_note:source"):
        source_row = fetch_note(db.connection(), note_id)

    if not source_row:
        raise ValueError(f"Source note with ID {note_id} not found")

    return _copy_note_recursive(db, source_row, new_parent_id)


def count_serialized_note_tree(note_data: Dict[str, Any]) -> int:
    if not note_data:
        return 0
    total = 1
    for child in note_data["children"] or []:
        total += count_serialized_note_tree(child)
    return total


def _copy_note_recursive(
    db: SafeSession,
    source_row: Dict[str, Any],
    new_parent_id: Optional[str],
) -> str:
    """Recursively duplicate ``source_row`` into a new subtree."""

    new_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)
    is_collapsed = bool(source_row["is_collapsed"])

    insert_note(
        db.connection(),
        note_id=new_id,
        content=source_row["content"],
        encryption_nonce=source_row["encryption_nonce"],
        encryption_tag=source_row["encryption_tag"],
        tags=source_row["tags"],
        tags_encryption_nonce=source_row["tags_encryption_nonce"],
        tags_encryption_tag=source_row["tags_encryption_tag"],
        parent_id=new_parent_id,
        prev_id=None,
        next_id=None,
        is_collapsed=is_collapsed,
        created_at=timestamp,
        updated_at=timestamp,
    )

    plaintext = get_cached_content(source_row["id"])

    cache_note(new_id, plaintext)

    tags_plaintext = get_cached_tags(source_row["id"])

    cache_note_tags(new_id, tags_plaintext)

    if note_store.loaded:
        note_store.add_note_from_db(
            SimpleNamespace(
                id=new_id,
                content=source_row["content"],
                encryption_nonce=source_row["encryption_nonce"],
                encryption_tag=source_row["encryption_tag"],
                tags=source_row["tags"],
                tags_encryption_nonce=source_row["tags_encryption_nonce"],
                tags_encryption_tag=source_row["tags_encryption_tag"],
                parent_id=new_parent_id,
                prev_id=None,
                next_id=None,
                is_collapsed=is_collapsed,
                created_at=timestamp,
                updated_at=timestamp,
            ),
            plaintext,
            tags_plaintext,
        )

    with SafeSession.allow_reads("copy_note:children"):
        children = fetch_children_ordered(db.connection(), source_row["id"])

    previous_child_id: Optional[str] = None
    for child_row in children:
        new_child_id = _copy_note_recursive(db, child_row, new_id)

        if previous_child_id:
            updated_at = datetime.now(timezone.utc)
            update_links(
                db.connection(),
                new_child_id,
                prev_id=previous_child_id,
                updated_at=updated_at,
            )
            update_links(
                db.connection(),
                previous_child_id,
                next_id=new_child_id,
                updated_at=updated_at,
            )

            if note_store.loaded:
                new_child_record = note_store.get_note(new_child_id)
                prev_record = note_store.get_note(previous_child_id)
                note_store.update_metadata_from_db(
                    SimpleNamespace(
                        id=new_child_record.id,
                        parent_id=new_child_record.parent_id,
                        prev_id=previous_child_id,
                        next_id=new_child_record.next_id,
                        created_at=new_child_record.created_at,
                        updated_at=new_child_record.updated_at,
                        is_collapsed=new_child_record.is_collapsed,
                    ),
                    rebuild=True,
                )
                note_store.update_metadata_from_db(
                    SimpleNamespace(
                        id=prev_record.id,
                        parent_id=prev_record.parent_id,
                        prev_id=prev_record.prev_id,
                        next_id=new_child_id,
                        created_at=prev_record.created_at,
                        updated_at=prev_record.updated_at,
                        is_collapsed=prev_record.is_collapsed,
                    ),
                    rebuild=True,
                )

        previous_child_id = new_child_id

    return new_id


def note_data_to_html(note_data: Dict[str, Any]) -> str:
    """
    Convert serialized note data to HTML using table structure for reliable indentation.
    Uses nested tables which create indentation that works across all applications.
    
    Args:
        note_data: Dictionary containing note content and children
        
    Returns:
        HTML string representation with guaranteed indentation
    """
    def render_note(note: Dict[str, Any], depth: int) -> str:
        """Render note using table structure for reliable indentation"""
        html_parts = []
        
        # Create indentation using table with spacer cell
        if depth > 0:
            spacer_width = depth * 32  # 32px per level
            html_parts.append('<table style="width: 100%; border-collapse: collapse; margin: 2px 0;"><tr>')
            html_parts.append(f'<td style="width: {spacer_width}px;"></td>')
            html_parts.append('<td>')
        
        # Add the note content with border
        if "content" not in note:
            raise RuntimeError(f"note_data missing required key: content | note={note}")
        content = note["content"]
        note_style = """
            border: 1px solid #cccccc;
            border-radius: 4px;
            padding: 8px 15px;
            margin: 2px 0;
            background: white;
        """
        html_parts.append(f'<div style="{note_style}">{content}</div>')
        
        # Close the table cell if indented
        if depth > 0:
            html_parts.append('</td></tr></table>')
        
        # Add children with increased depth
        if "children" not in note:
            raise RuntimeError(f"note_data missing required key: children | note={note}")
        children = note["children"]
        if not isinstance(children, list):
            raise TypeError(f"note_data.children must be a list: {type(children)}")
        for child in children:
            html_parts.append(render_note(child, depth + 1))
        
        return ''.join(html_parts)
    
    # Container with basic styling
    container_css = """
        font-family: system-ui, -apple-system, sans-serif;
        line-height: 1.5;
        color: #333333;
    """
    
    html = f'<div style="{container_css}">'
    html += render_note(note_data, 0)
    html += '</div>'
    
    return html


def note_data_to_plain_text(note_data: Dict[str, Any]) -> str:
    """
    Convert serialized note data to plain text with 4-space indentation.
    
    Args:
        note_data: Dictionary containing note content and children
        
    Returns:
        Plain text string with proper indentation
    """
    def render_note_text(note: Dict[str, Any], depth: int) -> list[str]:
        """Recursively render a note and its children as plain text"""
        lines = []
        indent = "    " * depth  # 4 spaces per level
        
        # Get content and strip HTML tags
        if "content" not in note:
            raise RuntimeError(f"note_data missing required key: content | note={note}")
        content = str(note["content"]).strip()
        if content:
            # Strip HTML tags but preserve text
            plain_content = re.sub(r'<[^>]+>', '', content)
            # Convert HTML entities
            plain_content = html.unescape(plain_content)
            # Handle line breaks
            plain_content = plain_content.replace('\n', f'\n{indent}')
            
            lines.append(f"{indent}{plain_content}")
        
        # Add children with increased depth
        if "children" not in note:
            raise RuntimeError(f"note_data missing required key: children | note={note}")
        children = note["children"]
        if not isinstance(children, list):
            raise TypeError(f"note_data.children must be a list: {type(children)}")
        for child in children:
            child_lines = render_note_text(child, depth + 1)
            lines.extend(child_lines)
        
        return lines
    
    all_lines = render_note_text(note_data, 0)
    return '\n'.join(all_lines)


def render_note_data_read_only(note_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a deep-copied note tree rendered in read-only mode."""

    def _render_node(node: Dict[str, Any]) -> Dict[str, Any]:
        content = node.get("content", "")
        note_obj = SimpleNamespace(content=content)
        rendered_content = render_read_only_mode(note_obj)

        rendered_children = []
        for child in node.get("children", []) or []:
            rendered_children.append(_render_node(child))

        rendered = dict(node)
        rendered["content"] = rendered_content
        rendered["children"] = rendered_children
        return rendered

    return _render_node(note_data)
