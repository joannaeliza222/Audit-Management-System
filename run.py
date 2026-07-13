import os

from app import create_app, db

app = create_app()

if __name__ == "__main__":
    # Never hardcode debug=True; use config/env only.
    app.run(debug=app.config.get('DEBUG', False), host='10.163.14.113', port=int(os.getenv('PORT', 5000)))
