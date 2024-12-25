from flask import Flask, render_template, request, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from pathlib import Path
from mako.lookup import TemplateLookup
from app.models.database import Base, engine, DBNote
from app.models.linked_list import LinkedListManager
import uuid

from api.flask_notes import notes_bp


app = Flask(__name__)

app.register_blueprint(notes_bp, url_prefix='/api/notes')

# Configure your database URI
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///your_database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Create the database tables
with app.app_context():
    Base.metadata.create_all(bind=engine)  # Ensure tables are created

# Set up Mako templates
templates = TemplateLookup(
    directories=[Path(__file__).parent / "templates"],
    module_directory=str(Path(__file__).parent / "__pycache__" / "mako_modules"),
    input_encoding="utf-8"
)

@app.route("/", methods=["GET"])
def home():
    session = scoped_session(sessionmaker(bind=engine))
    try:
        # Validate the linked list
        valid = LinkedListManager.validate_list(session, None)
        if not valid:
            raise Exception("List is invalid")

        # Build the tree of notes
        def build_tree(parent_id=None):
            notes = LinkedListManager.get_ordered_child_list(session, parent_id)
            return [{
                'id': note.id,
                'content': note.content,
                'parent_id': note.parent_id,
                'children': build_tree(note.id)  # Recursively get children
            } for note in notes]

        notes = build_tree(None)
        template = templates.get_template("index.html")
        return template.render(request=request, notes=notes, version="0.3.0")
    finally:
        session.remove()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8001, debug=True)