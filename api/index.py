"""Vercel Python entrypoint for the Flask application."""
import os

from app import app, db, init_database, Airport, UserAccount, Flight, Seat

# Create additive tables on startup, but seed demo records only when the protected
# Preview database is incomplete. Avoid repeatedly querying/seeding the entire
# sample airline fleet on every serverless cold start.
with app.app_context():
    db.create_all()
    if os.environ.get("SEED_DEMO_DATA", "").lower() in {"1", "true", "yes"}:
        demo_data_ready = (
            Airport.query.first() is not None
            and UserAccount.query.first() is not None
            and Flight.query.first() is not None
            and Seat.query.first() is not None
        )
        if not demo_data_ready:
            init_database()
