from flask import Blueprint, render_template
from app.utils.embeddings import login_required

# Create blueprint for chatbot pages
chatbot_pages_bp = Blueprint('chatbot_pages', __name__)

@chatbot_pages_bp.route('/enhanced-chatbot')
def enhanced_chatbot():
    """Enhanced AI Chatbot page"""
    import time
    return render_template('enhanced_chatbot_fixed.html', cache_buster=int(time.time()))
