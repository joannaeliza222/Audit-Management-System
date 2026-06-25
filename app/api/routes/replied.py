import io, os
import pandas as pd
from flask import Blueprint, request, session, redirect, render_template, url_for, flash, send_file, current_app
from sqlalchemy.exc import IntegrityError
from app.models import db, FAQ, DraftFAQ, DraftStatus
from app.utils.embeddings import (
    login_required,
    current_user,
    get_role,
    find_related_questions,
    normalize_text,
    encode_text,
    detect_future_issue,
    create_future_issue,
)

replied_bp = Blueprint("replied", __name__)


def _excel_safe(value):
    s = "" if value is None else str(value)
    if s.startswith(("=", "+", "-", "@")):
        return "'" + s
    return s



# -------------------------------
# Replied page
# -------------------------------

@replied_bp.route('/replied', methods=['GET', 'POST'])
@login_required
def replied():
    def _dedupe_rows(rows):
        """
        rows: iterable of (question, reply, memo_id, state_name)
        """
        out = []
        seen = set()
        for q, r, m, s in rows or []:
            key = (
                normalize_text(q or ""),
                (m or "").strip(),
                (s or "").strip(),
            )
            if key in seen:
                continue
            seen.add(key)
            out.append((q, r, m, s))
        return out

    role = get_role()
    user = current_user()
    # Viewer can access the page but must not search across tenants/states.
    # If "state_name" is omitted, viewers are implicitly scoped to their own state.
    related_questions = []
    related_count = 0
    keyword = None

    # Load distinct states once
    distinct_states = FAQ.query.with_entities(
        FAQ.state_name
    ).filter(
        FAQ.state_name.isnot(None),
        FAQ.state_name != '',
        FAQ.state_name != 'NaN',
        FAQ.state_name != 'nan',
        FAQ.state_name != 'None'
    ).distinct().order_by(FAQ.state_name).all()

    # Handle search queries with semantic search
    if request.method == 'GET':
        search_query = request.args.get('search', '').strip()
        
        if search_query:
            # Perform semantic search
            from app.utils.embeddings import get_embedding_model
            import numpy as np
            
            try:
                # Get embedding model
                embedding_model = get_embedding_model()
                
                # Generate embedding for search query
                search_embedding = embedding_model.encode([search_query])[0]
                
                # Get all FAQs with embeddings
                all_faqs = FAQ.query.filter(
                    FAQ.state_name.isnot(None),
                    FAQ.state_name != '',
                    FAQ.state_name != 'NaN',
                    FAQ.state_name != 'nan',
                    FAQ.state_name != 'None',
                    FAQ.embedding.isnot(None)
                ).all()
                
                # Calculate similarities
                search_results = []
                for faq in all_faqs:
                    if faq.embedding:
                        # Convert stored embedding back to numpy array
                        faq_embedding = np.array(faq.embedding)
                        
                        # Create combined text for search (subject + query_description)
                        search_text = f"{faq.subject or ''} {faq.query_description or ''}"
                        text_embedding = embedding_model.encode([search_text])[0]
                        
                        # Calculate cosine similarity
                        similarity = np.dot(search_embedding, text_embedding) / (
                            np.linalg.norm(search_embedding) * np.linalg.norm(text_embedding)
                        )
                        
                        search_results.append((faq, similarity))
                
                # Sort by similarity (descending) and filter by threshold
                search_results.sort(key=lambda x: x[1], reverse=True)
                filtered_results = [result for result in search_results if result[1] > 0.3]
                
                # Extract top results
                top_faqs = [result[0] for result in filtered_results[:20]]
                related_questions = _dedupe_rows([(f.subject, f.reply, f.memo_id, f.state_name) for f in top_faqs])
                related_count = len(related_questions)
                
                # Add search context
                search_performed = True
                search_query_display = search_query
                
            except Exception as e:
                current_app.logger.error(f"Semantic search error: {e}")
                # Fallback to text-based search
                all_faqs = FAQ.query.filter(
                    FAQ.state_name.isnot(None),
                    FAQ.state_name != '',
                    FAQ.state_name != 'NaN',
                    FAQ.state_name != 'nan',
                    FAQ.state_name != 'None',
                    (FAQ.subject.ilike(f'%{search_query}%') | FAQ.query_description.ilike(f'%{search_query}%'))
                ).order_by(FAQ.timestamp.desc()).all()
                
                related_questions = _dedupe_rows([(f.subject, f.reply, f.memo_id, f.state_name) for f in all_faqs])
                related_count = len(related_questions)
                search_performed = True
                search_query_display = search_query
        else:
            # Show all queries from FAQ table (main table)
            all_faqs = FAQ.query.filter(
                FAQ.state_name.isnot(None),
                FAQ.state_name != '',
                FAQ.state_name != 'NaN',
                FAQ.state_name != 'nan',
                FAQ.state_name != 'None'
            ).order_by(FAQ.timestamp.desc()).all()
            
            related_questions = _dedupe_rows([(f.subject, f.reply, f.memo_id, f.state_name) for f in all_faqs])
            related_count = len(related_questions)
            search_performed = False
            search_query_display = ''

    if request.method == 'POST':
        user_subject = request.form.get('subject', '').strip()
        memo_id = request.form.get('memo_id', '').strip()
        state_name = request.form.get('state_name', '').strip()
        download = request.form.get('download', '') == 'true'
        
        search_performed = False


        # Search mode - perform search if any criteria provided
        if user_subject or memo_id or state_name:
            search_performed = True
            
            text_matches = []
            if user_subject:
                pattern = f"%{user_subject}%"
                q = FAQ.query.filter(FAQ.subject.ilike(pattern))
                q = q.filter(FAQ.state_name.isnot(None))
                q = q.filter(FAQ.state_name != '')
                q = q.filter(FAQ.state_name != 'NaN')
                q = q.filter(FAQ.state_name != 'nan')
                q = q.filter(FAQ.state_name != 'None')
                if memo_id:
                    q = q.filter(FAQ.memo_id == memo_id)
                if state_name:
                    q = q.filter(FAQ.state_name == state_name)
                rows = q.limit(50).all()
                text_matches = [(f.subject, f.reply, f.memo_id, f.state_name) for f in rows]
            else:
                # If no subject search, apply memo_id and state_name filters
                q = FAQ.query.filter(FAQ.state_name.isnot(None))
                q = q.filter(FAQ.state_name != '')
                q = q.filter(FAQ.state_name != 'NaN')
                q = q.filter(FAQ.state_name != 'nan')
                q = q.filter(FAQ.state_name != 'None')
                if memo_id:
                    q = q.filter(FAQ.memo_id == memo_id)
                if state_name:
                    q = q.filter(FAQ.state_name == state_name)
                rows = q.limit(50).all()
                text_matches = [(f.subject, f.reply, f.memo_id, f.state_name) for f in rows]

            # Add semantic search if subject provided
            if user_subject:
                search_state = state_name if state_name else None
                vector_matches = find_related_questions(user_subject, None, memo_id, search_state)
                related_questions = _dedupe_rows(text_matches + (vector_matches or []))
            else:
                related_questions = _dedupe_rows(text_matches)

            if not related_questions:
                flash("No questions found matching your criteria.", "info")
        else:
            flash("Please enter search criteria to find questions.", "warning")

        # Download mode
        if download and related_questions:
            df = pd.DataFrame(
                related_questions,
                columns=["subject", "reply", "memo_id", "state_name"]
            )
            for col in ["subject", "reply", "memo_id", "state_name"]:
                if col in df.columns:
                    df[col] = df[col].map(_excel_safe)

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            output.seek(0)

            return send_file(
                output,
                as_attachment=True,
                download_name="related_questions.xlsx",
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

    return render_template(
        'replied.html',
        related_questions=related_questions,
        distinct_states=distinct_states,
        related_count=len(related_questions),
        search_performed=search_performed if 'search_performed' in locals() else False,
        search_query=search_query_display if 'search_query_display' in locals() else '',
        role=role
    )


@replied_bp.route('/add_single_question', methods=['POST'])
@login_required
def add_single_question():
    role = get_role()
    user = current_user()
    memo_id = request.form.get('memo_id', '').strip()
    state_name = request.form.get('state_name', '').strip()
    question = request.form.get('new_question', '').strip()
    reply = request.form.get('new_reply', '').strip()

    if not question:
        flash('Question cannot be empty', 'warning')
        return redirect(url_for('replied.replied'))

    # Modifier and viewer can only add for their own state
    # Admin and Reviewer can add for any state
    if role in ['modifier', 'viewer']:
        user_state = (user.state_name or '').strip()
        if not user_state:
            flash('Access denied: no state assigned. Please contact an administrator.', 'warning')
            return redirect(url_for('replied.replied'))
        # Enforce state restriction
        if state_name != user_state:
            flash('Access denied: you can only add questions for your own state.', 'warning')
            return redirect(url_for('replied.replied'))
        # Override state_name to ensure it matches user's state
        state_name = user_state

    if not state_name:
        flash('State name is required', 'warning')
        return redirect(url_for('replied.replied'))

    # Normalize and check duplicates
    normq = normalize_text(question)
    exists = FAQ.query.filter_by(
        norm_query=normq,
        state_name=state_name
    ).first()

    if exists:
        flash('Question already exists for this state!', 'warning')
        return redirect(url_for('replied.replied'))

    uploaded_by = session.get('username')

    # Create Draft With 384-dim PGVector embedding
    question_embedding = encode_text(question)

    draft = DraftFAQ(
        subject=question,
        query_description=question,
        norm_query=normq,
        reply=reply if reply else None,
        memo_id=memo_id,
        state_name=state_name,
        created_by=uploaded_by,
        status=DraftStatus.pending,
        embedding=question_embedding
    )

    try:
        db.session.add(draft)
        db.session.commit()

        if reply and detect_future_issue(reply):
            create_future_issue(
                description=f"Question: {question}(Reply: {reply})",
                related_draft_id=draft.id,
                version_detected=os.getenv("PORTAL_VERSION", None)
            )

        flash('Question added successfully!', 'success')


    except IntegrityError:
        db.session.rollback()
        flash('Duplicate question exists in drafts/faq', 'warning')

    return redirect(url_for('replied.replied'))
