from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required

document_qa_pages_bp = Blueprint('document_qa_pages', __name__)


@document_qa_pages_bp.route('/document-qa')
@login_required
def document_qa_page():
    """Render document Q&A page"""
    return render_template('document_qa.html')
