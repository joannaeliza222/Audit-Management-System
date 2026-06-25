"""
Cleanup utilities for maintenance tasks
"""
from datetime import datetime, timedelta
from app.models import FailedLoginAttempt, db
from flask import current_app


def cleanup_old_failed_attempts(days=30):
    """
    Delete failed login attempts older than specified days.
    Call this periodically (e.g., via cron or scheduled task).
    """
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        deleted_count = FailedLoginAttempt.query.filter(
            FailedLoginAttempt.attempt_time < cutoff
        ).delete()
        db.session.commit()
        current_app.logger.info(f"Cleaned up {deleted_count} old failed login attempts")
        return deleted_count
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error cleaning up failed login attempts: {e}")
        return 0


def cleanup_expired_password_reset_tokens():
    """
    Clean up expired password reset tokens.
    """
    try:
        cutoff = datetime.utcnow()
        from app.models import User
        expired_users = User.query.filter(
            User.password_reset_expires.isnot(None),
            User.password_reset_expires < cutoff
        ).all()
        
        count = 0
        for user in expired_users:
            user.password_reset_token = None
            user.password_reset_expires = None
            count += 1
        
        db.session.commit()
        current_app.logger.info(f"Cleaned up {count} expired password reset tokens")
        return count
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error cleaning up expired tokens: {e}")
        return 0
