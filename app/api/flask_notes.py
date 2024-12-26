from flask import Blueprint, request, jsonify, abort
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from app.models.database import DBNote, engine
from app.models.linked_list import LinkedListManager, MovePosition
import uuid

notes_bp = Blueprint('notes', __name__)

@notes_bp.route("/undo", methods=["POST"])
def undo():
    session = scoped_session(sessionmaker(bind=engine))
    try:
        command_stack = global_state["command_stack"]
        if command_stack.current_index >= 0:
            command_stack.undo(session)
            return jsonify({"status": "success", "message": "Undo successful"})
        else:
            return jsonify({"status": "noop", "message": "No actions to undo"})
    finally:
        session.remove()

@notes_bp.route("/redo", methods=["POST"])
def redo():
    session = scoped_session(sessionmaker(bind=engine))
    try:
        command_stack = global_state["command_stack"]
        if command_stack.current_index < len(command_stack.stack) - 1:
            command_stack.redo(session)
            return jsonify({"status": "success", "message": "Redo successful"})
        else:
            return jsonify({"status": "noop", "message": "No actions to redo"})
    finally:
        session.remove()

@notes_bp.route("/new", methods=["POST"])
def create_note_top():
    session = scoped_session(sessionmaker(bind=engine))
    try:
        note_id = str(uuid.uuid4())
        parent_id = request.json.get('parent_id', None)
        LinkedListManager.create_note_top(session, note_id, parent_id)
        session.commit()
        return jsonify({"id": note_id})
    except SQLAlchemyError as e:
        session.rollback()
        abort(500, description=str(e))
    finally:
        session.remove()

@notes_bp.route("/<note_id>", methods=["PUT"])
def update_note(note_id):
    session = scoped_session(sessionmaker(bind=engine))
    try:
        db_note = session.query(DBNote).filter(DBNote.id == note_id).first()
        if not db_note:
            abort(404, description="Note not found")
        db_note.content = request.json.get('content', '')
        session.commit()
        return jsonify({"id": db_note.id, "content": db_note.content})
    except SQLAlchemyError as e:
        session.rollback()
        abort(500, description=str(e))
    finally:
        session.remove()

@notes_bp.route("/<note_id>/move", methods=["POST"])
def move_note(note_id):
    session = scoped_session(sessionmaker(bind=engine))
    try:
        command = request.json
        note = session.get(DBNote, note_id)
        if not note:
            abort(404, description="Note not found")
        
        sibling_id = command.get('sibling_id')
        if sibling_id:
            sibling = session.get(DBNote, sibling_id)
            if not sibling:
                abort(404, description="Sibling note not found")
            if command.get('new_parent_id') != sibling.parent_id:
                abort(400, description="Sibling must be at the same level")
        
        position = None
        if command.get('position'):
            try:
                position = MovePosition[command['position'].upper()]
            except KeyError:
                abort(400, description="Invalid position value")

        LinkedListManager.move_note(
            db=session,
            note_id=note_id,
            new_parent_id=command.get('new_parent_id'),
            sibling_id=sibling_id,
            position=position
        )
        session.commit()
        return jsonify({"status": "success"})
    except ValueError as e:
        session.rollback()
        abort(400, description=str(e))
    finally:
        session.remove()

@notes_bp.route("/<note_id>", methods=["DELETE"])
def delete_note(note_id):
    session = scoped_session(sessionmaker(bind=engine))
    try:
        note = session.query(DBNote).filter(DBNote.id == note_id).first()
        if not note:
            abort(404, description="Note not found")
        
        LinkedListManager.delete_note(session, note_id)
        session.commit()
        return jsonify({"status": "success"})
    except SQLAlchemyError as e:
        session.rollback()
        abort(500, description=str(e))
    finally:
        session.remove()

@notes_bp.route("/new-drop", methods=["POST"])
def create_note_with_position():
    session = scoped_session(sessionmaker(bind=engine))
    try:
        command = request.json
        note_id = str(uuid.uuid4())
        LinkedListManager.create_note_drop(
            session, 
            note_id, 
            command.get('new_parent_id'),
            sibling_id=command.get('sibling_id'),
            position=MovePosition[command['position']] if command.get('position') else None
        )
        session.commit()
        return jsonify({"id": note_id})
    except SQLAlchemyError as e:
        session.rollback()
        abort(500, description=str(e))
    finally:
        session.remove()

@notes_bp.route("/new-sibling/<note_id>", methods=["POST"])
def create_new_sibling(note_id):
    session = scoped_session(sessionmaker(bind=engine))
    try:
        new_note_id = str(uuid.uuid4())
        LinkedListManager.create_note_top(session, new_note_id)
        
        note = session.query(DBNote).filter(DBNote.id == note_id).first()
        if not note:
            abort(404, description="Note not found")
        
        LinkedListManager.move_note(
            db=session,
            note_id=new_note_id,
            new_parent_id=note.parent_id,
            sibling_id=note_id,
            position=MovePosition.AFTER
        )
        session.commit()
        return jsonify({"id": new_note_id})
    except SQLAlchemyError as e:
        session.rollback()
        abort(500, description=str(e))
    finally:
        session.remove()

@notes_bp.route("/new-child/<note_id>", methods=["POST"])
def create_new_child(note_id):
    session = scoped_session(sessionmaker(bind=engine))
    try:
        new_note_id = str(uuid.uuid4())
        LinkedListManager.create_note_top(session, new_note_id)
        
        LinkedListManager.move_note(
            db=session,
            note_id=new_note_id,
            new_parent_id=note_id,
            sibling_id=None,
            position=None
        )
        session.commit()
        return jsonify({"id": new_note_id})
    except SQLAlchemyError as e:
        session.rollback()
        abort(500, description=str(e))
    finally:
        session.remove() 