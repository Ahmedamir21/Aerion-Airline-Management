"""Aerion Airline Management System - Flask application."""

from flask import Flask, request, redirect, url_for, flash, session, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
import random
import hashlib
import hmac
import secrets
import uuid
from datetime import timezone

app = Flask(__name__)

# Helper functions

def get_session(key, default=None):
    if not hasattr(get_session, "storage"):
        get_session.storage = {}
    return get_session.storage.get(key, default)

# Add helpers as template globals


# Never use a predictable development secret: a known Flask session key allows
# attackers to forge signed cookies and impersonate administrators.
# Configure SECRET_KEY in every deployed environment. The random fallback keeps
# local development/tests safe, but sessions will reset when the process restarts.
if os.environ.get('APP_ENV', '').lower() == 'production' and not os.environ.get('SECRET_KEY'):
    raise RuntimeError('SECRET_KEY must be configured in production')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or os.urandom(32)
app.config['WTF_CSRF_ENABLED'] = True
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', '').lower() in {'1', 'true', 'yes'}
# Use a managed database in hosted environments; SQLite remains the local default.
database_url = os.environ.get('DATABASE_URL', '').strip()
if database_url.startswith('postgres://'):
    database_url = 'postgresql://' + database_url[len('postgres://'):]
if database_url.startswith('postgresql://'):
    database_url = 'postgresql+psycopg://' + database_url[len('postgresql://'):]
if os.environ.get('VERCEL') and not database_url:
    raise RuntimeError('DATABASE_URL must be configured for Vercel deployments')
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///airline.db'
engine_options = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}
# Supabase transaction poolers may route successive statements to different server
# connections. Disable psycopg's automatic prepared statements for this URL mode.
if database_url.startswith('postgresql+psycopg://'):
    engine_options['connect_args'] = {'prepare_threshold': None}
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = engine_options
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['DEMO_MODE'] = os.environ.get('DEMO_MODE', os.environ.get('SEED_DEMO_DATA', 'false')).lower() in {'1', 'true', 'yes'}

db = SQLAlchemy(app)


@app.context_processor
def inject_csrf_token():
    """Expose a per-session synchronizer token to every HTML form."""
    def csrf_token():
        token = session.get('_csrf_token')
        if not token:
            token = secrets.token_urlsafe(32)
            session['_csrf_token'] = token
        return token
    return {'csrf_token': csrf_token}


@app.before_request
def protect_state_changing_requests():
    """Reject cross-site state-changing requests without a valid CSRF token."""
    if not app.config.get('WTF_CSRF_ENABLED', True) or request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        return None
    expected = session.get('_csrf_token')
    supplied = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
    if not expected or not supplied or not hmac.compare_digest(str(expected), str(supplied)):
        return 'Invalid or missing CSRF token', 400
    return None


@app.before_request
def enforce_role_access():
    """Require a valid database-backed role for every staff/admin operation."""
    path = request.path
    admin_only = (
        path.startswith('/admin/')
        or any(path == p or path.startswith(p + '/') for p in (
            '/admin-dashboard', '/employee-shifts', '/employee-qualifications',
            '/maintenance-work-orders', '/aircraft-defects'
        ))
    )
    staff_only = path.startswith('/staff/') or path == '/staff-dashboard'

    if admin_only:
        admin_id = session.get('admin_id')
        admin = UserAccount.query.filter_by(UserID=admin_id, Role='admin').first() if admin_id else None
        if not admin:
            session.pop('admin_id', None)
            return redirect(url_for('login'))

    if staff_only:
        staff_id = session.get('staff_id')
        employee = None
        if staff_id:
            employee = Employee.query.join(
                UserAccount, Employee.UserID == UserAccount.UserID
            ).filter(
                Employee.EmployeeID == staff_id,
                UserAccount.Role == 'staff'
            ).first()
        if not employee:
            session.pop('staff_id', None)
            return redirect(url_for('login'))


# ========================================
# DATABASE MODELS (no backref conflicts)
# ========================================

class UserAccount(db.Model):
    __tablename__ = 'UserAccount'
    UserID = db.Column(db.Integer, primary_key=True)
    Username = db.Column(db.String(50), unique=True, nullable=False)
    Password = db.Column(db.String(255), nullable=False)
    Role = db.Column(db.String(20), nullable=False)


class Passenger(db.Model):
    __tablename__ = 'Passenger'
    PassengerID = db.Column(db.Integer, primary_key=True)
    UserID = db.Column(db.Integer, db.ForeignKey('UserAccount.UserID'), unique=True, nullable=False)
    Name = db.Column(db.String(100), nullable=False)
    PassportNumber = db.Column(db.String(20), nullable=False)
    ContactInfo = db.Column(db.String(200), nullable=True)


class Employee(db.Model):
    __tablename__ = 'Employee'
    EmployeeID = db.Column(db.Integer, primary_key=True)
    UserID = db.Column(db.Integer, db.ForeignKey('UserAccount.UserID'), unique=True, nullable=False)
    Name = db.Column(db.String(100), nullable=False)
    Position = db.Column(db.String(50), nullable=False)
    PhoneExtension = db.Column(db.String(10), nullable=True)


class CrewMember(db.Model):
    __tablename__ = 'CrewMember'
    CrewID = db.Column(db.Integer, primary_key=True)
    UserID = db.Column(db.Integer, db.ForeignKey('UserAccount.UserID'), unique=True, nullable=False)
    Name = db.Column(db.String(100), nullable=False)
    Role = db.Column(db.String(50), nullable=False)
    LicenseNumber = db.Column(db.String(30), nullable=True)
    Base = db.Column(db.String(50), nullable=True)


class Airport(db.Model):
    __tablename__ = 'Airport'
    AirportID = db.Column(db.Integer, primary_key=True)
    Code = db.Column(db.String(10), unique=True, nullable=False)
    Name = db.Column(db.String(100), nullable=False)
    City = db.Column(db.String(50), nullable=False)
    Country = db.Column(db.String(50), nullable=True)


class Route(db.Model):
    __tablename__ = 'Route'
    RouteID = db.Column(db.Integer, primary_key=True)
    DepartureAirportID = db.Column(db.Integer, db.ForeignKey('Airport.AirportID'))
    ArrivalAirportID = db.Column(db.Integer, db.ForeignKey('Airport.AirportID'))
    Distance = db.Column(db.Integer)
    BaseFare = db.Column(db.Float, nullable=False)
    DepartureAirport = db.relationship('Airport', foreign_keys=[DepartureAirportID])
    ArrivalAirport = db.relationship('Airport', foreign_keys=[ArrivalAirportID])


class Aircraft(db.Model):
    __tablename__ = 'Aircraft'
    AircraftID = db.Column(db.Integer, primary_key=True)
    RegistrationNumber = db.Column(db.String(20), unique=True, nullable=False)
    Model = db.Column(db.String(50), nullable=False)
    TotalSeats = db.Column(db.Integer, nullable=False)
    SeatConfiguration = db.Column(db.String(50), nullable=True)


class Flight(db.Model):
    __tablename__ = 'Flight'
    FlightID = db.Column(db.Integer, primary_key=True)
    RouteID = db.Column(db.Integer, db.ForeignKey('Route.RouteID'))
    AircraftID = db.Column(db.Integer, db.ForeignKey('Aircraft.AircraftID'))
    FlightNumber = db.Column(db.String(10), nullable=False)
    DepartureTime = db.Column(db.DateTime, nullable=False)
    ArrivalTime = db.Column(db.DateTime, nullable=False)
    Status = db.Column(db.String(20), nullable=False, default='on_time')
    FareClass = db.Column(db.String(30), nullable=True)
    Route = db.relationship('Route', foreign_keys=[RouteID])
    Aircraft = db.relationship('Aircraft', foreign_keys=[AircraftID])


class Seat(db.Model):
    __tablename__ = 'Seat'
    SeatID = db.Column(db.Integer, primary_key=True)
    FlightID = db.Column(db.Integer, db.ForeignKey('Flight.FlightID'), nullable=False)
    SeatNumber = db.Column(db.String(10), nullable=False)
    Class = db.Column(db.String(20), nullable=False)
    IsAvailable = db.Column(db.Boolean, default=True)

    __table_args__ = (db.UniqueConstraint('FlightID', 'SeatNumber'),)


class Booking(db.Model):
    __tablename__ = 'Booking'
    BookingID = db.Column(db.Integer, primary_key=True)
    PassengerID = db.Column(db.Integer, db.ForeignKey('Passenger.PassengerID'), nullable=False)
    FlightID = db.Column(db.Integer, db.ForeignKey('Flight.FlightID'), nullable=False)
    NumberOfSeats = db.Column(db.Integer, nullable=False)
    TotalAmount = db.Column(db.Float, nullable=False)
    BookingDate = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
    Status = db.Column(db.String(20), nullable=False, default='confirmed')
    Passenger = db.relationship('Passenger', foreign_keys=[PassengerID])
    Flight = db.relationship('Flight', foreign_keys=[FlightID])


class Ticket(db.Model):
    __tablename__ = 'Ticket'
    TicketID = db.Column(db.Integer, primary_key=True)
    BookingID = db.Column(db.Integer, db.ForeignKey('Booking.BookingID'), nullable=False, unique=True)
    PassengerID = db.Column(db.Integer, db.ForeignKey('Passenger.PassengerID'), nullable=False)
    FlightID = db.Column(db.Integer, db.ForeignKey('Flight.FlightID'), nullable=False)
    SeatNumber = db.Column(db.String(10), nullable=False)
    FarePaid = db.Column(db.Float, nullable=False)
    IssueDate = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
    Status = db.Column(db.String(20), nullable=False, default='issued')


class Payment(db.Model):
    __tablename__ = 'Payment'
    PaymentID = db.Column(db.Integer, primary_key=True)
    BookingID = db.Column(db.Integer, db.ForeignKey('Booking.BookingID'), nullable=False)
    Amount = db.Column(db.Float, nullable=False)
    PaymentMethod = db.Column(db.String(50), nullable=True)
    PaymentDate = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
    TransactionID = db.Column(db.String(50), nullable=True, unique=True)


class Refund(db.Model):
    __tablename__ = 'Refund'
    RefundID = db.Column(db.Integer, primary_key=True)
    BookingID = db.Column(db.Integer, db.ForeignKey('Booking.BookingID'), nullable=False)
    PaymentID = db.Column(db.Integer, db.ForeignKey('Payment.PaymentID'), nullable=False, unique=True)
    Amount = db.Column(db.Float, nullable=False)
    RefundDate = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
    Reason = db.Column(db.String(200), nullable=False, default='Booking cancellation')
    TransactionID = db.Column(db.String(60), nullable=False, unique=True)
    Status = db.Column(db.String(20), nullable=False, default='simulated')


class Baggage(db.Model):
    __tablename__ = 'Baggage'
    BaggageID = db.Column(db.Integer, primary_key=True)
    TicketID = db.Column(db.Integer, db.ForeignKey('Ticket.TicketID'), nullable=False)
    TagNumber = db.Column(db.String(20), nullable=False)
    Weight = db.Column(db.Float, nullable=True)
    Status = db.Column(db.String(20), nullable=False, default='checked')
    CheckedDate = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=True)


class LoyaltyAccount(db.Model):
    __tablename__ = 'LoyaltyAccount'
    LoyaltyID = db.Column(db.Integer, primary_key=True)
    PassengerID = db.Column(db.Integer, db.ForeignKey('Passenger.PassengerID'), unique=True, nullable=False)
    MilesBalance = db.Column(db.Integer, default=0, nullable=False)
    MilesEarnedTotal = db.Column(db.Integer, default=0, nullable=False)
    LastEarnedDate = db.Column(db.DateTime, nullable=True)
    LastRedeemedDate = db.Column(db.DateTime, nullable=True)


# ========================================
# QUERY HELPERS (no backref conflicts)
# ========================================

def get_passenger_by_user(user_id):
    """Get passenger by user ID."""
    return db.session.query(Passenger).filter_by(UserID=user_id).first()


def get_employee_by_user(user_id):
    """Get employee by user ID."""
    return db.session.query(Employee).filter_by(UserID=user_id).first()


def get_crew_by_user(user_id):
    """Get crew member by user ID."""
    return db.session.query(CrewMember).filter_by(UserID=user_id).first()


def get_flights_by_route(route_id):
    """Get flights by route ID."""
    return db.session.query(Flight).filter_by(RouteID=route_id).all()


def get_seats_by_flight(flight_id):
    """Get seats by flight ID."""
    return db.session.query(Seat).filter_by(FlightID=flight_id)


def get_bookings_by_passenger(passenger_id):
    """Get bookings by passenger ID."""
    return db.session.query(Booking).filter_by(PassengerID=passenger_id).order_by(Booking.BookingDate.desc()).all()


def get_tickets_by_booking(booking_id):
    """Get tickets by booking ID."""
    return db.session.query(Ticket).filter_by(BookingID=booking_id).first()


def get_baggage_by_ticket(ticket_id):
    """Get baggage by ticket ID."""
    return db.session.query(Baggage).filter_by(TicketID=ticket_id).first()


def get_loyalty_by_passenger(passenger_id):
    """Get loyalty account by passenger ID."""
    return db.session.query(LoyaltyAccount).filter_by(PassengerID=passenger_id).first()


def get_airport_by_code(code):
    """Get airport by code."""
    return db.session.query(Airport).filter_by(Code=code).first()


def get_aircraft_by_id(aircraft_id):
    """Get aircraft by ID."""
    return db.session.get(Aircraft, aircraft_id)


def get_route_by_ids(dep_id, arr_id):
    """Get route by airport IDs."""
    return db.session.query(Route).filter(
        (Route.DepartureAirportID == dep_id) &
        (Route.ArrivalAirportID == arr_id)
    ).first()


# ========================================
# HELPER FUNCTIONS
# ========================================

from werkzeug.security import generate_password_hash, check_password_hash

from werkzeug.security import generate_password_hash, check_password_hash



# ========================================
# ADDITIONAL AIRLINE OPERATIONS MODELS
# ========================================

class EmployeeQualification(db.Model):
    __tablename__ = 'EmployeeQualification'
    QualificationID = db.Column(db.Integer, primary_key=True)
    EmployeeID = db.Column(db.Integer, db.ForeignKey('Employee.EmployeeID'), nullable=False)
    QualificationName = db.Column(db.String(50), nullable=False)
    AuthorizedAircraftType = db.Column(db.String(50), nullable=True)
    IssuedDate = db.Column(db.DateTime, nullable=True)
    ExpiryDate = db.Column(db.DateTime, nullable=True)

class EmployeeShift(db.Model):
    __tablename__ = 'EmployeeShift'
    ShiftID = db.Column(db.Integer, primary_key=True)
    EmployeeID = db.Column(db.Integer, db.ForeignKey('Employee.EmployeeID'), nullable=False)
    Date = db.Column(db.Date, nullable=False)
    ShiftType = db.Column(db.String(20), nullable=False)  # morning, afternoon, night
    Status = db.Column(db.String(20), nullable=False, default='assigned')
    AssignedTask = db.Column(db.String(100), nullable=True)

class MaintenanceWorkOrder(db.Model):
    __tablename__ = 'MaintenanceWorkOrder'
    WorkOrderID = db.Column(db.Integer, primary_key=True)
    AircraftID = db.Column(db.Integer, db.ForeignKey('Aircraft.AircraftID'), nullable=False)
    Description = db.Column(db.String(200), nullable=False)
    Severity = db.Column(db.String(20), nullable=False)  # minor, major, critical
    Status = db.Column(db.String(20), nullable=False, default='pending')  # pending, in_progress, completed, blocked
    ReportedDate = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    ResolvedDate = db.Column(db.DateTime, nullable=True)
    AssignedTechnicianID = db.Column(db.Integer, db.ForeignKey('Employee.EmployeeID'), nullable=True)
    ApprovedByID = db.Column(db.Integer, db.ForeignKey('Employee.EmployeeID'), nullable=True)
    ApprovalDate = db.Column(db.DateTime, nullable=True)

class AircraftDefect(db.Model):
    __tablename__ = 'AircraftDefect'
    DefectID = db.Column(db.Integer, primary_key=True)
    AircraftID = db.Column(db.Integer, db.ForeignKey('Aircraft.AircraftID'), nullable=False)
    Description = db.Column(db.String(200), nullable=False)
    Severity = db.Column(db.String(20), nullable=False)  # minor, major, critical
    Status = db.Column(db.String(20), nullable=False, default='reported')  # reported, under_repair, cleared
    ReportedDate = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    ResolvedDate = db.Column(db.DateTime, nullable=True)
    RelatedWorkOrderID = db.Column(db.Integer, db.ForeignKey('MaintenanceWorkOrder.WorkOrderID'), nullable=True)


class AuditLog(db.Model):
    __tablename__ = 'AuditLog'
    AuditID = db.Column(db.Integer, primary_key=True)
    ActorUserID = db.Column(db.Integer, db.ForeignKey('UserAccount.UserID'), nullable=True)
    ActorUsername = db.Column(db.String(50), nullable=False, default='system')
    Action = db.Column(db.String(100), nullable=False)
    EntityType = db.Column(db.String(80), nullable=False)
    EntityID = db.Column(db.String(80), nullable=True)
    Details = db.Column(db.Text, nullable=True)
    CreatedAt = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)

class SavedFilter(db.Model):
    __tablename__ = 'SavedFilter'
    FilterID = db.Column(db.Integer, primary_key=True)
    UserID = db.Column(db.Integer, db.ForeignKey('UserAccount.UserID'), nullable=False, index=True)
    Name = db.Column(db.String(80), nullable=False)
    QueryString = db.Column(db.String(1000), nullable=False, default='')
    CreatedAt = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    __table_args__ = (db.UniqueConstraint('UserID', 'Name', name='uq_saved_filter_user_name'),)

class FareClass(db.Model):
    __tablename__ = 'FareClass'
    FareClassID = db.Column(db.Integer, primary_key=True)
    Code = db.Column(db.String(30), unique=True, nullable=False)
    Name = db.Column(db.String(60), nullable=False)
    Multiplier = db.Column(db.Float, nullable=False, default=1.0)
    Active = db.Column(db.Boolean, nullable=False, default=True)

class RouteWaypoint(db.Model):
    __tablename__ = 'RouteWaypoint'
    WaypointID = db.Column(db.Integer, primary_key=True)
    RouteID = db.Column(db.Integer, db.ForeignKey('Route.RouteID'), nullable=False, index=True)
    Sequence = db.Column(db.Integer, nullable=False)
    Label = db.Column(db.String(100), nullable=False)
    Latitude = db.Column(db.Float, nullable=False)
    Longitude = db.Column(db.Float, nullable=False)
    PlannedAltitudeFt = db.Column(db.Integer, nullable=False, default=30000)
    PlannedSpeedKts = db.Column(db.Integer, nullable=False, default=450)
    StopAirportID = db.Column(db.Integer, db.ForeignKey('Airport.AirportID'), nullable=True)
    __table_args__ = (db.UniqueConstraint('RouteID', 'Sequence', name='uq_route_waypoint_sequence'),)

class ImportBatch(db.Model):
    __tablename__ = 'ImportBatch'
    BatchID = db.Column(db.Integer, primary_key=True)
    UploadedByUserID = db.Column(db.Integer, db.ForeignKey('UserAccount.UserID'), nullable=True)
    FileName = db.Column(db.String(255), nullable=False)
    TotalRows = db.Column(db.Integer, nullable=False, default=0)
    ImportedRows = db.Column(db.Integer, nullable=False, default=0)
    RejectedRows = db.Column(db.Integer, nullable=False, default=0)
    Status = db.Column(db.String(20), nullable=False, default='validated')
    CreatedAt = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

# Fix the db.create_all reference to include new tables
from seatmap import build_plan, seat_list

# Loyalty: every 40 miles can be exchanged for a 10% discount (max 3 units = 30%).
MILES_PER_DISCOUNT = 40
DISCOUNT_PER_UNIT = 10
MAX_DISCOUNT_UNITS = 3
DEFAULT_MULTIPLIERS = {'economy': 1.0, 'premium_economy': 1.45, 'business': 2.8, 'first': 4.5}
CLOSED_STATUSES = {'cancelled', 'completed', 'arrived', 'departed'}


def class_multiplier(code):
    """Price multiplier for a cabin class (FareClass table, with safe fallback)."""
    row = FareClass.query.filter_by(Code=code, Active=True).first()
    return float(row.Multiplier) if row else DEFAULT_MULTIPLIERS.get(code, 1.0)


def seat_prices(route):
    """Price of one seat per cabin: BaseFare is the economy price."""
    base = float(route.BaseFare or 0)
    return {c: round(base * class_multiplier(c), 2) for c in ('economy', 'business')}


def safe_next(target):
    """Only allow local paths as a post-login redirect (no open redirect)."""
    target = (target or '').strip()
    if target.startswith('/') and not target.startswith('//') and '\\' not in target and '\n' not in target:
        return target
    return None


@app.context_processor
def inject_next():
    return {'next_url': safe_next(request.values.get('next')) or ''}


def _asset_version():
    try:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
        return str(int(max(os.path.getmtime(os.path.join(base, f)) for f in ('css/style.css', 'js/main.js'))))
    except OSError:
        return '1'


ASSET_V = _asset_version()


@app.context_processor
def inject_asset_version():
    return {'asset_v': ASSET_V}


def hash_password(password):
    """Hash a password for storage."""
    return generate_password_hash(password)

def verify_password(password, hashed_password):
    """Verify modern Werkzeug hashes or legacy SHA-256 hashes."""
    if not isinstance(hashed_password, str):
        return False
    try:
        if check_password_hash(hashed_password, password):
            return True
    except (ValueError, TypeError):
        pass
    return hashlib.sha256(password.encode('utf-8')).hexdigest() == hashed_password


# ========================================
# DATABASE INITIALIZATION
# ========================================

def init_airports():
    """Initialize airports if not already present."""
    airports_data = [
        ('CAI', 'Cairo International', 'Cairo', 'Egypt'),
        ('LON', 'Heathrow', 'London', 'UK'),
        ('PAR', 'Charles de Gaulle', 'Paris', 'France'),
        ('NYC', 'John F. Kennedy', 'New York', 'USA'),
        ('DUB', 'Dubai International', 'Dubai', 'UAE'),
        ('FRA', 'Frankfurt Airport', 'Frankfurt', 'Germany'),
        ('DXB', 'DXB', 'Dubai', 'UAE'),
        ('AMS', 'Amsterdam Schiphol', 'Amsterdam', 'Netherlands'),
        ('IST', 'Istanbul Airport', 'Istanbul', 'Turkey'),
        ('BCN', 'Barcelona-El Prat', 'Barcelona', 'Spain'),
    ]
    for code, name, city, country in airports_data:
        existing = Airport.query.filter_by(Code=code).first()
        if not existing:
            db.session.add(Airport(Code=code, Name=name, City=city, Country=country))
    db.session.commit()


def init_aircraft():
    """Initialize aircraft if not already present."""
    aircraft_data = [
        ('A320', 180, '3-2'),
        ('B737', 189, '3-2'),
        ('A321', 220, '2-3'),
        ('B777', 380, '3-3'),
        ('A330', 300, '2-4'),
    ]
    for model, seats, config in aircraft_data:
        # Keep initialization idempotent: don't add another seed aircraft of the same model.
        existing = Aircraft.query.filter_by(Model=model).first()
        if not existing:
            reg_num = model[:3] + str(random.randint(100, 999))
            while Aircraft.query.filter_by(RegistrationNumber=reg_num).first():
                reg_num = model[:3] + str(random.randint(100, 999))
            db.session.add(Aircraft(
                RegistrationNumber=reg_num, Model=model, TotalSeats=seats, SeatConfiguration=config))
    db.session.commit()


def init_routes():
    """Initialize routes if not already present."""
    init_airports()
    
    aircraft_list = Aircraft.query.all()
    route_data = [
        ('CAI', 'NYC', 9500),
        ('CAI', 'LON', 3500),
        ('CAI', 'PAR', 3000),
        ('CAI', 'DUB', 3100),
        ('CAI', 'FRA', 3300),
        ('LON', 'NYC', 5500),
        ('LON', 'PAR', 340),
        ('PAR', 'NYC', 6200),
        ('DUB', 'NYC', 11000),
        ('IST', 'CAI', 2300),
    ]
    
    dep_airports = {'CAI', 'LON', 'PAR', 'DUB', 'IST'}
    arr_airports = {'NYC', 'LON', 'PAR', 'DUB', 'FRA', 'IST', 'BCN'}
    
    for dep_code, arr_code, distance in route_data:
        dep_airport = Airport.query.filter_by(Code=dep_code).first()
        arr_airport = Airport.query.filter_by(Code=arr_code).first()
        if dep_airport and arr_airport:
            existing = get_route_by_ids(dep_airport.AirportID, arr_airport.AirportID)
            if not existing:
                aircraft = random.choice(aircraft_list) if aircraft_list else None
                db.session.add(Route(
                    DepartureAirportID=dep_airport.AirportID,
                    ArrivalAirportID=arr_airport.AirportID,
                    Distance=distance,
                    BaseFare=random.uniform(200, 1500)
                ))
    db.session.commit()


def init_flights():
    """Initialize flights if not already present."""
    init_routes()
    aircraft_list = Aircraft.query.all()
    routes = Route.query.all()
    base_date = datetime.now()
    
    for i, route in enumerate(routes):
        # Avoid duplicating seeded flights whenever the app is initialized again.
        if Flight.query.filter_by(RouteID=route.RouteID).first():
            continue
        num_flights = random.randint(2, 5)
        for j in range(num_flights):
            days_offset = j * 3 + (i % 7)
            departure_time = base_date + timedelta(days=days_offset, hours=random.randint(6, 22))
            arrival_time = departure_time + timedelta(hours=random.randint(2, 12))
            
            aircraft = random.choice(aircraft_list) if aircraft_list else None
            fare_class = random.choice(['economy', 'business', 'first']) if route.Distance > 5000 else 'economy'
            
            flight = Flight(
                RouteID=route.RouteID,
                AircraftID=aircraft.AircraftID if aircraft else None,
                FlightNumber='EY{:03d}'.format(random.randint(100, 999)),
                DepartureTime=departure_time,
                ArrivalTime=arrival_time,
                Status=random.choice(['on_time', 'on_time', 'on_time', 'delayed']),
                FareClass=fare_class
            )
            db.session.add(flight)
    db.session.commit()


def init_seats():
    """Initialize seats for all flights."""
    flights = Flight.query.all()
    for flight in flights:
        aircraft = get_aircraft_by_id(flight.AircraftID) if flight.AircraftID else None
        total_seats = aircraft.TotalSeats if aircraft else 180
        
        # Check if seats already exist
        existing = get_seats_by_flight(flight.FlightID).first()
        if existing:
            continue
        
        for number, seat_class in seat_list(total_seats):
            db.session.add(Seat(FlightID=flight.FlightID, SeatNumber=number,
                                Class=seat_class, IsAvailable=True))
    db.session.commit()


def init_users():
    """Initialize users if not already present."""
    if UserAccount.query.count() > 0:
        return
    
    passenger_names = [
        ('Ahmed', '0123456789'),
        ('Sara', '0123456788'),
        ('Mohamed', '0123456787'),
        ('Fatma', '0123456786'),
        ('Khaled', '0123456785'),
    ]
    
    passengers = []
    for i, (name, passport) in enumerate(passenger_names):
        user = UserAccount(
            Username='passenger{}'.format(i + 1),
            Password=hash_password('password123'),
            Role='passenger'
        )
        db.session.add(user)
        db.session.flush()
        
        passenger = Passenger(
            UserID=user.UserID,
            Name=name,
            PassportNumber=passport,
            ContactInfo='contact{}@example.com'.format(i + 1)
        )
        db.session.add(passenger)
        passengers.append(passenger)
    
    db.session.commit()
    
    # Create loyalty accounts after passengers are committed
    for passenger in passengers:
        loyalty = LoyaltyAccount(PassengerID=passenger.PassengerID)
        db.session.add(loyalty)
    db.session.commit()
    
    # Create staff
    staff_names = ['Mohamed', 'Aisha', 'Omar']
    for i, name in enumerate(staff_names):
        existing = UserAccount.query.filter_by(Username='staff{}'.format(i + 1)).first()
        if not existing:
            user = UserAccount(
                Username='staff{}'.format(i + 1),
                Password=hash_password('password123'),
                Role='staff'
            )
            db.session.add(user)
            db.session.flush()
            
            employee = Employee(
                UserID=user.UserID,
                Name=name,
                Position='staff',
                PhoneExtension=str(5000 + i)
            )
            db.session.add(employee)
    db.session.commit()
    
    # Create admin
    existing_admin = UserAccount.query.filter_by(Username='admin1').first()
    if not existing_admin:
        admin_user = UserAccount(
            Username='admin1',
            Password=hash_password('admin123'),
            Role='admin'
        )
        db.session.add(admin_user)
        db.session.flush()
        
        admin_employee = Employee(
            UserID=admin_user.UserID,
            Name='Admin User',
            Position='admin',
            PhoneExtension='5000'
        )
        db.session.add(admin_employee)
    db.session.commit()
    
    # Create crew members
    crew_names = [
        ('Captain Hassan', 'pilot'),
        ('Captain Amal', 'pilot'),
        ('Cabin Lead', 'cabin_attendant'),
        ('Cabin Member 1', 'cabin_attendant'),
    ]
    
    for i, (name, role) in enumerate(crew_names):
        existing_crew = CrewMember.query.filter_by(Name=name).first()
        if not existing_crew:
            user = UserAccount(
                Username='crew{}'.format(i + 1),
                Password=hash_password('password123'),
                Role='staff'
            )
            db.session.add(user)
            db.session.flush()
            
            crew = CrewMember(
                UserID=user.UserID,
                Name=name,
                Role=role,
                LicenseNumber='LIC-{:05d}'.format(random.randint(10000, 99999)),
                Base=random.choice(['Cairo', 'London', 'Dubai'])
            )
            db.session.add(crew)
    db.session.commit()


def init_bookings_tickets():
    """Initialize sample bookings and tickets."""
    passengers = db.session.query(Passenger).all()
    flights = Flight.query.all()
    
    if not passengers or not flights:
        return
    
    for passenger in passengers[:3]:
        num_bookings = random.randint(1, 2)
        selected_flights = random.sample(flights, min(num_bookings, len(flights)))
        
        for flight in selected_flights:
            num_seats = random.randint(1, 2)
            available_seats = get_seats_by_flight(flight.FlightID).filter(
                Seat.IsAvailable == True
            ).limit(num_seats).all()
            
            if not available_seats:
                continue
            
            total_amount = round(sum(random.uniform(150, 500) for _ in available_seats), 2)
            
            booking = Booking(
                PassengerID=passenger.PassengerID,
                FlightID=flight.FlightID,
                NumberOfSeats=num_seats,
                TotalAmount=total_amount,
                Status='confirmed'
            )
            db.session.add(booking)
            db.session.flush()
            
            seat_numbers = [s.SeatNumber for s in available_seats[:num_seats]]
            for taken_seat in available_seats[:num_seats]:
                taken_seat.IsAvailable = False
            for sn in seat_numbers:
                fare_paid = round(random.uniform(150, 500), 2)
                ticket = Ticket(
                    BookingID=booking.BookingID,
                    PassengerID=passenger.PassengerID,
                    FlightID=flight.FlightID,
                    SeatNumber=sn,
                    FarePaid=fare_paid,
                    Status='issued'
                )
                db.session.add(ticket)
                
                baggage_status = random.choice(['checked', 'checked', 'checked', 'in_transit'])
                baggage = Baggage(
                    TicketID=ticket.TicketID,
                    TagNumber='BAG{}'.format(random.randint(1000, 9999)),
                    Weight=round(random.uniform(15, 30), 1),
                    Status=baggage_status
                )
            db.session.add(baggage)
                
                # Update loyalty miles
            loyalty = get_loyalty_by_passenger(passenger.PassengerID)
            if loyalty and flight.Route:
                    miles_earned = int(flight.Route.Distance / 100)
                    loyalty.MilesBalance += miles_earned
                    loyalty.MilesEarnedTotal += miles_earned
                    loyalty.LastEarnedDate = datetime.now(timezone.utc).replace(tzinfo=None)
    
    db.session.commit()


def init_database():
    """Initialize the database and generate sample data."""
    with app.app_context():
        db.create_all()
        init_airports()
        init_aircraft()
        init_routes()
        init_flights()
        init_seats()
        init_users()


# ========================================
# ROUTES
# ========================================


def reserve_seat_atomically(flight_id, seat_number, passenger_id):
    """Atomically reserve a seat using a conditional database UPDATE.

    SQLAlchemy renders correctly quoted identifiers for both PostgreSQL and SQLite.
    The database evaluates availability and updates the seat in one statement, so
    simultaneous requests cannot both reserve the same seat.
    """
    with app.app_context():
        from sqlalchemy import update

        statement = update(Seat).where(
            Seat.FlightID == flight_id,
            Seat.SeatNumber == seat_number,
            Seat.IsAvailable.is_(True)
        ).values(IsAvailable=False)
        result = db.session.execute(statement)

        if result.rowcount > 0:
            db.session.commit()
            seat = db.session.query(Seat).filter(
                Seat.FlightID == flight_id,
                Seat.SeatNumber == seat_number
            ).first()
            return True, seat

        db.session.rollback()
        return False, None

@app.after_request
def add_security_headers(response):
    """Basic hardening headers; no CSP because pages load CDN fonts and icons."""
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    if request.path.startswith('/static/') and response.status_code == 200:
        # Assets are versioned with ?v=..., so browsers and the Vercel edge may keep them.
        response.headers['Cache-Control'] = 'public, max-age=31536000, s-maxage=31536000, immutable'
    return response


@app.route('/healthz')
def healthz():
    """Lightweight platform health check that reports database availability safely."""
    from sqlalchemy import text
    try:
        db.session.execute(text('SELECT 1'))
        return jsonify({'status': 'ok', 'database': 'ok'}), 200
    except Exception:
        db.session.rollback()
        app.logger.exception("Health check database query failed")
        return jsonify({'status': 'unavailable', 'database': 'error'}), 503


@app.route('/')
def index():
    """Home page - landing page for the airline management system."""
    try:
        airports = Airport.query.order_by(Airport.Code).all()
    except Exception:
        airports = []
    return render_template('index.html', airports=airports)


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Self-service sign up. Only passenger accounts can be created here;
    staff and admin accounts are created by an admin."""
    if request.method == 'POST':
        import re as _re
        name = (request.form.get('name') or '').strip()
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        confirm = request.form.get('confirm_password') or ''
        passport = (request.form.get('passport') or '').strip().upper()
        contact = (request.form.get('contact') or '').strip()

        error = None
        if not name or len(name) > 100:
            error = 'Enter your full name'
        elif not _re.fullmatch(r'[A-Za-z0-9_.-]{3,50}', username):
            error = 'Username must be 3-50 characters: letters, numbers, dot, dash or underscore'
        elif len(password) < 8 or len(password) > 128:
            error = 'Password must be at least 8 characters'
        elif password != confirm:
            error = 'Passwords do not match'
        elif not _re.fullmatch(r'[A-Z0-9]{5,20}', passport):
            error = 'Enter a valid passport number (letters and digits only)'
        elif len(contact) > 200:
            error = 'Contact info is too long'
        elif UserAccount.query.filter_by(Username=username).first():
            error = 'Username already exists'

        if error:
            flash(error, 'error')
            return render_template('register.html', form=request.form), 400

        try:
            user = UserAccount(Username=username, Password=hash_password(password), Role='passenger')
            db.session.add(user)
            db.session.flush()
            passenger = Passenger(UserID=user.UserID, Name=name, PassportNumber=passport,
                                  ContactInfo=contact or None)
            db.session.add(passenger)
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash('Could not create the account. Try a different username.', 'error')
            return render_template('register.html', form=request.form), 400

        session.clear()
        session['passenger_id'] = passenger.PassengerID
        flash('Account created. Welcome aboard.', 'success')
        return redirect(safe_next(request.form.get('next')) or url_for('passenger_dashboard'))

    return render_template('register.html', form={})


# In-memory login throttling. On serverless hosting this is per instance,
# so it slows guessing down but is not a hard global limit.
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_SECONDS = 300
_LOGIN_FAILURES = {}


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page for all user types."""
    if request.method == 'POST':
        # Prevent role/session carry-over when switching accounts or retrying login.
        session.clear()
        username = request.form.get('username')
        password = request.form.get('password')

        # Throttle repeated failures per client and username.
        import time as _time
        _key = ((request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or request.remote_addr or '')
                + '|' + (username or '').lower())
        _now = _time.time()
        _hits = [t for t in _LOGIN_FAILURES.get(_key, []) if _now - t < LOGIN_LOCK_SECONDS]
        _LOGIN_FAILURES[_key] = _hits
        if len(_hits) >= LOGIN_MAX_FAILURES:
            flash('Too many failed attempts. Try again in a few minutes.', 'error')
            return render_template('login.html'), 429

        user = None
        # Try verifying against all users with matching username using verify_password
        candidates = UserAccount.query.filter_by(Username=username).all()
        for candidate in candidates:
            if verify_password(password, candidate.Password):
                # Upgrade legacy SHA-256 hashes immediately after successful authentication.
                if len(candidate.Password) == 64 and all(c in '0123456789abcdef' for c in candidate.Password.lower()):
                    candidate.Password = hash_password(password)
                    db.session.commit()
                user = candidate
                break

        if user:
            _LOGIN_FAILURES.pop(_key, None)
            if user.Role == 'passenger':
                passenger = get_passenger_by_user(user.UserID)
                if passenger:
                    session['passenger_id'] = passenger.PassengerID
            elif user.Role == 'staff':
                employee = get_employee_by_user(user.UserID)
                if employee:
                    session['staff_id'] = employee.EmployeeID
            elif user.Role == 'admin':
                session['admin_id'] = user.UserID

            nxt = safe_next(request.form.get('next'))
            if nxt and user.Role in ('passenger', 'staff'):
                return redirect(nxt)
            if user.Role == 'passenger':
                return redirect(url_for('passenger_dashboard'))
            elif user.Role == 'staff':
                return redirect(url_for('staff_dashboard'))
            elif user.Role == 'admin':
                return redirect(url_for('admin_dashboard'))
        else:
            _LOGIN_FAILURES.setdefault(_key, []).append(_now)
            flash('Invalid username or password', 'error')

    return render_template('login.html')


@app.route('/passenger-dashboard')
def passenger_dashboard():
    """Passenger dashboard - home page for logged-in passengers."""
    passenger_id = session.get('passenger_id')
    if not passenger_id:
        return redirect(url_for('login'))

    passenger = db.session.get(Passenger, passenger_id)
    if not passenger:
        return redirect(url_for('login'))

    bookings = get_bookings_by_passenger(passenger.PassengerID)

    loyalty = get_loyalty_by_passenger(passenger.PassengerID)

    upcoming = []
    past = []
    for booking in bookings:
        flight = db.session.get(Flight, booking.FlightID)
        if flight and flight.DepartureTime > datetime.now(timezone.utc).replace(tzinfo=None):
            ticket = get_tickets_by_booking(booking.BookingID)
            upcoming.append({
                'booking': booking,
                'flight': flight,
                'ticket': ticket
            })
        else:
            ticket = get_tickets_by_booking(booking.BookingID)
            past.append({
                'booking': booking,
                'flight': flight,
                'ticket': ticket
            })

    return render_template(
        'passenger_dashboard.html',
        passenger=passenger,
        bookings=bookings,
        upcoming_bookings=upcoming,
        past_bookings=past,
        loyalty=loyalty
    )


@app.route('/staff-dashboard')
def staff_dashboard():
    """Staff dashboard for airline employees."""
    staff_id = session.get('staff_id')
    if not staff_id:
        return redirect(url_for('login'))

    employee = get_employee_by_user(staff_id) or db.session.get(Employee, staff_id)
    if not employee:
        return redirect(url_for('login'))

    flights = Flight.query.order_by(Flight.DepartureTime.desc()).all()
    bookings = Booking.query.order_by(Booking.BookingDate.desc()).all()
    available_seats = {
        flight.FlightID: db.session.query(db.func.count(Seat.SeatID)).filter(
            Seat.FlightID == flight.FlightID, Seat.IsAvailable.is_(True)
        ).scalar() or 0
        for flight in flights
    }
    passenger_names = {
        passenger.PassengerID: passenger.Name
        for passenger in Passenger.query.all()
    }

    return render_template(
        'staff_dashboard.html',
        employee=employee,
        flights=flights,
        bookings=bookings,
        total_flights=len(flights),
        available_seats=available_seats,
        passenger_names=passenger_names
    )


@app.route('/admin-dashboard')
def admin_dashboard():
    """Administrator dashboard - full control panel."""
    admin_id = session.get('admin_id')
    if not admin_id:
        return redirect(url_for('login'))

    total_passengers = Passenger.query.count()
    total_flights = Flight.query.count()
    total_airports = Airport.query.count()
    total_routes = Route.query.count()

    total_revenue = db.session.query(db.func.sum(Ticket.FarePaid)).scalar() or 0

    status_counts = db.session.query(Flight.Status, db.func.count(Flight.FlightID)).group_by(Flight.Status).all()

    recent_bookings = Booking.query.order_by(Booking.BookingDate.desc()).limit(10).all()
    loyalty_accounts = LoyaltyAccount.query.all()
    total_miles = sum(account.MilesBalance for account in loyalty_accounts)
    avg_miles = total_miles / len(loyalty_accounts) if loyalty_accounts else 0

    users = UserAccount.query.order_by(UserAccount.Role, UserAccount.Username).all()

    flights_with_seats = []
    for flight in Flight.query.limit(20).all():
        available = db.session.query(db.func.count(Seat.SeatID)).filter(
            Seat.FlightID == flight.FlightID,
            Seat.IsAvailable == True
        ).scalar() or 0
        total = db.session.query(db.func.count(Seat.SeatID)).filter(
            Seat.FlightID == flight.FlightID
        ).scalar() or 0
        flights_with_seats.append({
            'flight': flight,
            'available': available,
            'total': total
        })

    return render_template(
        'admin_dashboard.html',
        total_passengers=total_passengers,
        total_flights=total_flights,
        total_airports=total_airports,
        total_routes=total_routes,
        total_revenue=round(total_revenue, 2),
        status_counts=status_counts,
        recent_bookings=recent_bookings,
        users=users,
        flights_with_seats=flights_with_seats,
        total_miles=total_miles,
        avg_miles=round(avg_miles, 1),
        Passenger=Passenger
    )


# ========================================
# PASSENGER WORKFLOWS
# ========================================

@app.route('/passenger/search-flights', methods=['GET', 'POST'])
def passenger_search_flights():
    """Search flights. Origin and date are optional; at least one airport is needed."""
    from sqlalchemy.orm import joinedload
    src = request.form if request.method == 'POST' else request.args
    origin = (src.get('origin') or '').strip().upper()
    destination = (src.get('destination') or '').strip().upper()
    date_str = (src.get('date') or '').strip()
    airports = Airport.query.order_by(Airport.City, Airport.Code).all()

    if not origin and not destination:
        if request.method == 'POST' or request.args:
            flash('Pick a departure or an arrival airport', 'error')
        return render_template('search_flights.html', airports=airports)

    by_code = {a.Code: a for a in airports}
    if origin and origin == destination:
        flash('Choose different departure and arrival airports', 'error')
        return redirect(url_for('passenger_search_flights'))
    if (origin and origin not in by_code) or (destination and destination not in by_code):
        flash('Choose valid airports', 'error')
        return redirect(url_for('passenger_search_flights'))

    date = None
    if date_str:
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            flash('Enter a valid departure date', 'error')
            return redirect(url_for('passenger_search_flights'))

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start = max(date, now) if date else now
    query = Flight.query.options(
        joinedload(Flight.Route).joinedload(Route.DepartureAirport),
        joinedload(Flight.Route).joinedload(Route.ArrivalAirport),
        joinedload(Flight.Aircraft),
    ).join(Route, Flight.RouteID == Route.RouteID).filter(
        Flight.DepartureTime >= now,
        Flight.Status.notin_(list(CLOSED_STATUSES)),
    )
    if origin:
        query = query.filter(Route.DepartureAirportID == by_code[origin].AirportID)
    if destination:
        query = query.filter(Route.ArrivalAirportID == by_code[destination].AirportID)
    flights = query.filter(Flight.DepartureTime >= start).order_by(Flight.DepartureTime.asc()).limit(40).all()
    fell_back = False
    if date and not flights:
        # Nothing on or after that date: show the nearest upcoming flights instead.
        fell_back = True
        flights = query.order_by(Flight.DepartureTime.asc()).limit(40).all()

    seat_counts = {f.FlightID: {'economy': 0, 'business': 0} for f in flights}
    if flights:
        rows = db.session.query(Seat.FlightID, Seat.Class, db.func.count(Seat.SeatID)).filter(
            Seat.FlightID.in_(list(seat_counts)), Seat.IsAvailable.is_(True)
        ).group_by(Seat.FlightID, Seat.Class).all()
        for fid, cls, n in rows:
            key = 'business' if cls == 'business' else 'economy'
            seat_counts[fid][key] += n
    prices = {f.FlightID: seat_prices(f.Route) for f in flights}
    on_date = bool(date and flights and not fell_back and flights[0].DepartureTime.date() == date.date())
    return render_template(
        'search_results.html', flights=flights, origin=origin, destination=destination,
        date=date, origin_airport=by_code.get(origin), dest_airport=by_code.get(destination),
        seat_counts=seat_counts, prices=prices, on_date=on_date,
    )


@app.route('/passenger/book/<int:flight_id>', methods=['GET', 'POST'])
def passenger_book_flight(flight_id):
    """Pick seats on the cabin map. Passengers book for themselves; staff book at the counter."""
    flight = db.get_or_404(Flight, flight_id)
    passenger_id = session.get('passenger_id')
    staff_id = session.get('staff_id')

    if session.get('admin_id') and not (passenger_id or staff_id):
        flash('Administrators manage flights. Log in as a passenger or staff member to book.', 'error')
        return redirect(url_for('admin_dashboard'))
    if not (passenger_id or staff_id):
        flash('Please log in to book this flight. We will bring you back to the seat map.', 'info')
        return redirect(url_for('login', next=request.path))
    is_staff = bool(staff_id and not passenger_id)

    if flight.Status.lower() in CLOSED_STATUSES or flight.DepartureTime <= datetime.now(timezone.utc).replace(tzinfo=None):
        flash('This flight is no longer available for booking', 'error')
        return redirect(url_for('passenger_search_flights'))
    if not flight.Route or flight.Route.BaseFare is None or flight.Route.BaseFare <= 0:
        flash('This flight does not have a valid fare configured', 'error')
        return redirect(url_for('passenger_search_flights'))

    prices = seat_prices(flight.Route)
    loyalty = get_loyalty_by_passenger(passenger_id) if passenger_id else None
    miles = loyalty.MilesBalance if loyalty else 0
    max_units = min(MAX_DISCOUNT_UNITS, miles // MILES_PER_DISCOUNT)

    if request.method == 'POST':
        seat_numbers = request.form.getlist('seats')
        if len(seat_numbers) == 1 and ',' in seat_numbers[0]:
            seat_numbers = [v.strip() for v in seat_numbers[0].split(',') if v.strip()]
        seat_numbers = list(dict.fromkeys(v.strip().upper() for v in seat_numbers if v.strip()))
        if not seat_numbers:
            flash('Please select at least one seat', 'error')
            return redirect(request.url)
        if len(seat_numbers) > 9:
            flash('You can book up to 9 seats at once', 'error')
            return redirect(request.url)

        if is_staff:
            username = (request.form.get('passenger_username') or '').strip()
            owner = UserAccount.query.filter_by(Username=username, Role='passenger').first() if username else None
            passenger = get_passenger_by_user(owner.UserID) if owner else None
            if not passenger:
                flash('Enter the username of an existing passenger to book for them', 'error')
                return redirect(request.url)
        else:
            passenger = db.session.get(Passenger, passenger_id)
            if not passenger:
                session.pop('passenger_id', None)
                return redirect(url_for('login', next=request.path))

        payment_method = (request.form.get('payment_method') or ('cash' if is_staff else 'card')).strip().lower()
        if payment_method not in {'card', 'cash', 'bank_transfer'}:
            flash('Choose a valid payment method', 'error')
            return redirect(request.url)

        units = 0
        if not is_staff:
            try:
                units = int(request.form.get('miles_units') or 0)
            except ValueError:
                units = 0
            units = max(0, min(units, max_units))

        # One conditional UPDATE and all inserts share one transaction, so either
        # every selected seat is booked or nothing is saved.
        reserved = db.session.query(Seat).filter(
            Seat.FlightID == flight_id, Seat.SeatNumber.in_(seat_numbers), Seat.IsAvailable.is_(True)
        ).update({Seat.IsAvailable: False}, synchronize_session=False)
        if reserved != len(seat_numbers):
            db.session.rollback()
            flash('Some of those seats were just taken. Please pick again.', 'error')
            return redirect(request.url)

        chosen = {x.SeatNumber: x for x in db.session.query(Seat).filter(
            Seat.FlightID == flight_id, Seat.SeatNumber.in_(seat_numbers)).all()}
        discount = units * DISCOUNT_PER_UNIT / 100.0
        passenger_loyalty = get_loyalty_by_passenger(passenger.PassengerID)
        base_miles = max(int((flight.Route.Distance or 0) / 100), 0)
        booking_ids, total = [], 0.0

        for number in seat_numbers:
            seat_class = chosen[number].Class
            list_price = round(float(flight.Route.BaseFare) * class_multiplier(seat_class), 2)
            fare_paid = round(list_price * (1 - discount), 2)
            total += fare_paid
            booking = Booking(PassengerID=passenger.PassengerID, FlightID=flight_id,
                              NumberOfSeats=1, TotalAmount=fare_paid, Status='confirmed')
            db.session.add(booking)
            db.session.flush()
            booking_ids.append(booking.BookingID)
            # Demo coursework app: a payment row is recorded, no real gateway is contacted.
            db.session.add(Payment(BookingID=booking.BookingID, Amount=fare_paid,
                                   PaymentMethod=payment_method, TransactionID='PAY-' + uuid.uuid4().hex))
            ticket = Ticket(BookingID=booking.BookingID, PassengerID=passenger.PassengerID,
                            FlightID=flight_id, SeatNumber=number, FarePaid=fare_paid, Status='issued')
            db.session.add(ticket)
            db.session.flush()
            db.session.add(Baggage(TicketID=ticket.TicketID, TagNumber='BAG{}'.format(random.randint(1000, 9999)),
                                   Weight=round(random.uniform(15, 30), 1), Status='checked'))
            if passenger_loyalty:
                earned = base_miles * (2 if seat_class == 'business' else 1)
                passenger_loyalty.MilesBalance += earned
                passenger_loyalty.MilesEarnedTotal += earned
                passenger_loyalty.LastEarnedDate = datetime.now(timezone.utc).replace(tzinfo=None)

        if units and passenger_loyalty:
            passenger_loyalty.MilesBalance -= units * MILES_PER_DISCOUNT
            passenger_loyalty.LastRedeemedDate = datetime.now(timezone.utc).replace(tzinfo=None)

        db.session.commit()
        msg = 'Booked seat{} {} on {}. Total ${:,.2f}{}.'.format(
            's' if len(seat_numbers) > 1 else '', ', '.join(seat_numbers), flight.FlightNumber, total,
            ' ({}% miles discount applied)'.format(units * DISCOUNT_PER_UNIT) if units else '')
        flash(msg, 'success')
        if is_staff:
            return redirect(url_for('staff_dashboard'))
        return redirect(url_for('passenger_my_bookings'))

    aircraft = flight.Aircraft
    total_seats = aircraft.TotalSeats if aircraft else 180
    seats = db.session.query(Seat.SeatNumber, Seat.IsAvailable).filter(Seat.FlightID == flight_id).all()
    existing = {n for n, _ in seats}
    taken = {n for n, free in seats if not free}
    free_count = len(existing) - len(taken)
    return render_template(
        'book_flight.html', flight=flight, plan=build_plan(total_seats), prices=prices,
        taken=taken, existing=existing, free_count=free_count, total_seats=len(existing),
        miles=miles, max_units=max_units, is_staff=is_staff,
        miles_per=MILES_PER_DISCOUNT, per_unit=DISCOUNT_PER_UNIT, aircraft=aircraft,
    )


@app.route('/passenger/my-bookings')
def passenger_my_bookings():
    """View passenger's bookings and tickets."""
    passenger_id = session.get('passenger_id')
    if not passenger_id:
        return redirect(url_for('login'))

    passenger = Passenger.query.get(passenger_id)
    if not passenger:
        return redirect(url_for('login'))

    bookings = get_bookings_by_passenger(passenger.PassengerID)

    booking_details = []
    for booking in bookings:
        flight = db.session.query(Flight).get(booking.FlightID)
        ticket = get_tickets_by_booking(booking.BookingID)
        baggage = get_baggage_by_ticket(ticket.TicketID) if ticket else None
        payment = Payment.query.filter_by(BookingID=booking.BookingID).first()
        refund = Refund.query.filter_by(BookingID=booking.BookingID).first()

        booking_details.append({
            'booking': booking,
            'flight': flight,
            'ticket': ticket,
            'baggage': baggage,
            'payment': payment,
            'refund': refund
        })

    loyalty = get_loyalty_by_passenger(passenger.PassengerID)

    return render_template(
        'my_bookings.html',
        passenger=passenger,
        booking_details=booking_details,
        loyalty=loyalty,
        now=datetime.now(timezone.utc).replace(tzinfo=None)
    )


@app.route('/passenger/cancel-booking/<int:booking_id>', methods=['POST'])
def passenger_cancel_booking(booking_id):
    """Cancel a booking."""
    booking = db.get_or_404(Booking, booking_id)

    passenger_id = session.get('passenger_id')
    if not passenger_id or booking.PassengerID != passenger_id:
        flash('Unauthorized', 'error')
        return redirect(url_for('passenger_dashboard'))

    if booking.Status == 'cancelled':
        flash('This booking is already cancelled', 'info')
        return redirect(url_for('passenger_my_bookings'))

    flight = db.session.get(Flight, booking.FlightID)
    if flight and flight.DepartureTime <= datetime.now(timezone.utc).replace(tzinfo=None):
        flash('A booking cannot be cancelled after the flight has departed', 'error')
        return redirect(url_for('passenger_my_bookings'))

    booking.Status = 'cancelled'
    ticket = get_tickets_by_booking(booking.BookingID)
    if ticket:
        ticket.Status = 'cancelled'
        seat = db.session.query(Seat).filter_by(
            FlightID=ticket.FlightID,
            SeatNumber=ticket.SeatNumber
        ).first()
        if seat:
            seat.IsAvailable = True

    payment = Payment.query.filter_by(BookingID=booking.BookingID).first()
    if payment and not Refund.query.filter_by(PaymentID=payment.PaymentID).first():
        db.session.add(Refund(
            BookingID=booking.BookingID,
            PaymentID=payment.PaymentID,
            Amount=payment.Amount,
            Reason='Passenger booking cancellation',
            TransactionID='REF-' + uuid.uuid4().hex,
            Status='simulated'
        ))

    db.session.commit()

    flash('Booking cancelled. Any refund is recorded as a demo transaction; no real payment provider is contacted.', 'success')
    return redirect(url_for('passenger_my_bookings'))


# ========================================
# STAFF WORKFLOWS
# ========================================

@app.route('/staff/check-in/<int:booking_id>', methods=['GET', 'POST'])
def staff_check_in(booking_id):
    """Check in a passenger, optionally assign a seat, and register baggage."""
    booking = Booking.query.get_or_404(booking_id)
    flight = db.get_or_404(Flight, booking.FlightID)
    ticket = get_tickets_by_booking(booking.BookingID)

    if request.method == 'POST':
        new_seat = (request.form.get('new_seat') or '').strip()
        baggage_tag = (request.form.get('baggage_tag') or '').strip()
        baggage_weight = request.form.get('baggage_weight', type=float)

        if new_seat and (not ticket or new_seat != ticket.SeatNumber):
            result = db.session.query(Seat).filter(
                Seat.FlightID == booking.FlightID,
                Seat.SeatNumber == new_seat,
                Seat.IsAvailable.is_(True)
            ).update({Seat.IsAvailable: False}, synchronize_session=False)
            if result != 1:
                db.session.rollback()
                flash('Selected seat is unavailable', 'error')
                return redirect(request.url)

            if ticket and ticket.SeatNumber:
                old_seat = Seat.query.filter_by(
                    FlightID=booking.FlightID, SeatNumber=ticket.SeatNumber
                ).first()
                if old_seat:
                    old_seat.IsAvailable = True

            if ticket:
                ticket.SeatNumber = new_seat
            else:
                ticket = Ticket(
                    BookingID=booking.BookingID,
                    PassengerID=booking.PassengerID,
                    FlightID=booking.FlightID,
                    SeatNumber=new_seat,
                    FarePaid=round(booking.TotalAmount / max(booking.NumberOfSeats, 1), 2),
                    Status='checked_in'
                )
                db.session.add(ticket)
                db.session.flush()

        if not ticket:
            db.session.rollback()
            flash('Assign an available seat before checking in this booking', 'error')
            return redirect(request.url)

        if baggage_tag or baggage_weight is not None:
            if not baggage_tag or baggage_weight is None or baggage_weight <= 0:
                db.session.rollback()
                flash('Enter both a baggage tag and a positive weight', 'error')
                return redirect(request.url)
            if get_baggage_by_ticket(ticket.TicketID):
                db.session.rollback()
                flash('Baggage is already registered for this ticket', 'error')
                return redirect(request.url)
            db.session.add(Baggage(
                TicketID=ticket.TicketID,
                TagNumber=baggage_tag,
                Weight=baggage_weight,
                Status='checked'
            ))

        ticket.Status = 'checked_in'
        booking.Status = 'checked_in'
        db.session.commit()
        flash('Passenger checked in successfully. Seat: {}'.format(ticket.SeatNumber), 'success')
        return redirect(url_for('staff_dashboard'))

    available_seats = db.session.query(Seat).filter(
        Seat.FlightID == booking.FlightID,
        Seat.IsAvailable.is_(True)
    ).order_by(Seat.SeatNumber.asc()).limit(10).all()

    return render_template(
        'staff_check_in.html',
        booking=booking,
        flight=flight,
        available_seats=available_seats,
        ticket=ticket
    )


@app.route('/staff/register-baggage/<int:booking_id>', methods=['GET', 'POST'])
def staff_register_baggage(booking_id):
    """Register a checked bag for a passenger with an issued ticket."""
    booking = Booking.query.get_or_404(booking_id)
    ticket = get_tickets_by_booking(booking.BookingID)

    if request.method == 'POST':
        if not ticket:
            flash('A ticket is required before registering baggage', 'error')
            return redirect(request.url)

        tag_number = (request.form.get('tag_number') or '').strip()
        weight = request.form.get('weight', type=float)
        if not tag_number:
            tag_number = 'BAG{}'.format(random.randint(1000, 9999))
        if weight is None or weight <= 0:
            flash('Enter a positive baggage weight', 'error')
            return redirect(request.url)

        if get_baggage_by_ticket(ticket.TicketID):
            flash('Baggage already registered', 'error')
            return redirect(request.url)

        db.session.add(Baggage(
            TicketID=ticket.TicketID,
            TagNumber=tag_number,
            Weight=weight,
            Status='checked'
        ))
        db.session.commit()
        flash('Baggage registered successfully. Tag: {}'.format(tag_number), 'success')
        return redirect(url_for('staff_dashboard'))

    return render_template('staff_register_baggage.html', booking=booking, ticket=ticket)


@app.route('/staff/set-flight-status/<int:flight_id>', methods=['POST'])
def set_flight_status(flight_id):
    """Set a flight's status (on time, delayed, cancelled)."""
    flight = Flight.query.get_or_404(flight_id)

    status = request.form.get('status')
    if status in ['on_time', 'delayed', 'cancelled']:
        flight.Status = status
        db.session.commit()
        flash('Flight {} status set to {}'.format(flight.FlightNumber, status), 'success')
    else:
        flash('Invalid status', 'error')

    return redirect(url_for('staff_dashboard'))


@app.route('/staff/passenger-list/<int:flight_id>')
def staff_passenger_list(flight_id):
    """Show the passenger list for a flight."""
    flight = Flight.query.get_or_404(flight_id)

    bookings = Booking.query.filter_by(FlightID=flight_id).order_by(Booking.BookingDate.asc()).all()

    passenger_info = []
    for booking in bookings:
        passenger = get_passenger_by_user(booking.PassengerID) or db.session.get(Passenger, booking.PassengerID)
        ticket = get_tickets_by_booking(booking.BookingID)

        passenger_info.append({
            'passenger': passenger,
            'booking': booking,
            'ticket': ticket,
            'baggage': get_baggage_by_ticket(ticket.TicketID) if ticket else None,
            'seat': ticket.SeatNumber if ticket else 'Not assigned'
        })

    return render_template('staff_passenger_list.html', flight=flight, passenger_info=passenger_info)


# ========================================
# ADMIN WORKFLOWS
# ========================================

@app.route('/admin/add-airport', methods=['GET', 'POST'])
def admin_add_airport():
    """Add a new airport."""
    if request.method == 'POST':
        code = (request.form.get('code') or '').strip().upper()
        name = (request.form.get('name') or '').strip()
        city = (request.form.get('city') or '').strip()
        country = (request.form.get('country') or 'Egypt').strip()
        if not code or not name or not city:
            flash('Airport code, name, and city are required', 'error')
            return redirect(request.url)

        existing = Airport.query.filter_by(Code=code).first()
        if existing:
            flash('Airport code already exists', 'error')
            return redirect(request.url)

        airport = Airport(Code=code, Name=name, City=city, Country=country)
        db.session.add(airport)
        db.session.commit()

        flash('Airport added successfully', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin_add_airport.html')


@app.route('/admin/add-route', methods=['GET', 'POST'])
def admin_add_route():
    """Add a new route."""
    init_airports()
    airports = Airport.query.all()

    if request.method == 'POST':
        departure = (request.form.get('departure_airport') or '').strip().upper()
        arrival = (request.form.get('arrival_airport') or '').strip().upper()
        distance = request.form.get('distance', type=float)
        base_fare = request.form.get('base_fare', type=float)
        if (not departure or not arrival or departure == arrival
                or distance is None or distance <= 0
                or base_fare is None or base_fare <= 0):
            flash('Choose different airports and enter positive distance and fare values', 'error')
            return redirect(request.url)

        dep_airport = Airport.query.filter_by(Code=departure).first()
        arr_airport = Airport.query.filter_by(Code=arrival).first()

        if not dep_airport or not arr_airport:
            flash('Invalid airport selection', 'error')
            return redirect(request.url)

        existing = get_route_by_ids(dep_airport.AirportID, arr_airport.AirportID)
        if existing:
            flash('Route already exists', 'error')
            return redirect(request.url)

        route = Route(
            DepartureAirportID=dep_airport.AirportID,
            ArrivalAirportID=arr_airport.AirportID,
            Distance=distance,
            BaseFare=base_fare
        )
        db.session.add(route)
        db.session.commit()

        flash('Route added successfully', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin_add_route.html', airports=airports)


@app.route('/admin/add-aircraft', methods=['GET', 'POST'])
def admin_add_aircraft():
    """Add a new aircraft."""
    if request.method == 'POST':
        model = (request.form.get('model') or '').strip()
        total_seats = request.form.get('total_seats', type=int)
        seat_config = (request.form.get('seat_config') or '2-2').strip()
        if not model or total_seats is None or total_seats < 1:
            flash('Enter an aircraft model and a positive seat count', 'error')
            return redirect(request.url)
        if not all(part.isdigit() and int(part) > 0 for part in seat_config.split('-')) or len(seat_config.split('-')) != 2:
            flash('Seat configuration must contain two positive numbers, such as 3-2', 'error')
            return redirect(request.url)

        reg_number = model[:3].upper() + str(random.randint(100, 999))
        while Aircraft.query.filter_by(RegistrationNumber=reg_number).first():
            reg_number = model[:3].upper() + str(random.randint(100, 9999))

        aircraft = Aircraft(
            RegistrationNumber=reg_number,
            Model=model,
            TotalSeats=total_seats,
            SeatConfiguration=seat_config
        )
        db.session.add(aircraft)
        db.session.commit()

        flash('Aircraft added successfully', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin_add_aircraft.html')


@app.route('/admin/add-flight', methods=['GET', 'POST'])
def admin_add_flight():
    """Add a new flight."""
    routes = Route.query.all()

    if request.method == 'POST':
        route_id = request.form.get('route_id', type=int)
        aircraft_id = request.form.get('aircraft_id', type=int)
        flight_number = (request.form.get('flight_number') or '').strip().upper()
        departure_time = request.form.get('departure_time')
        arrival_time = request.form.get('arrival_time')
        status = request.form.get('status', 'on_time')
        fare_class = request.form.get('fare_class', 'economy')

        route = db.session.get(Route, route_id) if route_id else None
        aircraft = db.session.get(Aircraft, aircraft_id) if aircraft_id else None
        if not route or not aircraft or not flight_number:
            flash('Select a valid route and aircraft and enter a flight number', 'error')
            return redirect(request.url)
        if Flight.query.filter_by(FlightNumber=flight_number).first():
            flash('Flight number already exists', 'error')
            return redirect(request.url)
        if status not in {'on_time', 'delayed', 'cancelled'}:
            flash('Invalid flight status', 'error')
            return redirect(request.url)
        active_fare_codes = {x.Code for x in FareClass.query.filter_by(Active=True).all()}
        if fare_class not in ({'economy', 'premium_economy', 'business', 'first'} | active_fare_codes):
            flash('Invalid or inactive fare class', 'error')
            return redirect(request.url)
        try:
            dep = datetime.fromisoformat(departure_time) if departure_time else None
            arr = datetime.fromisoformat(arrival_time) if arrival_time else None
        except ValueError:
            dep, arr = None, None
        if not dep or not arr or dep >= arr:
            flash('Enter valid departure and arrival times; arrival must be later', 'error')
            return redirect(request.url)
        if status != 'cancelled':
            overlap = Flight.query.filter(
                Flight.AircraftID == aircraft_id,
                Flight.Status.notin_(['cancelled', 'completed']),
                Flight.DepartureTime < arr,
                Flight.ArrivalTime > dep
            ).first()
            if overlap:
                flash(f'This aircraft is already assigned to overlapping flight {overlap.FlightNumber}.', 'error')
                return redirect(request.url)
            grounded_defect = AircraftDefect.query.filter(
                AircraftDefect.AircraftID == aircraft_id, AircraftDefect.Severity == 'critical',
                AircraftDefect.Status != 'cleared'
            ).first()
            grounded_order = MaintenanceWorkOrder.query.filter(
                MaintenanceWorkOrder.AircraftID == aircraft_id, MaintenanceWorkOrder.Severity == 'critical',
                MaintenanceWorkOrder.Status != 'completed'
            ).first()
            if grounded_defect or grounded_order:
                flash('This aircraft cannot be scheduled while a critical maintenance issue is unresolved.', 'error')
                return redirect(request.url)

        flight = Flight(
            RouteID=route_id,
            AircraftID=aircraft_id,
            FlightNumber=flight_number,
            DepartureTime=dep,
            ArrivalTime=arr,
            Status=status,
            FareClass=fare_class
        )
        db.session.add(flight)
        db.session.flush()

        # Generate seats for this flight
        aircraft = Aircraft.query.get(aircraft_id)
        seat_config = aircraft.SeatConfiguration if aircraft else '2-2'

        parts = seat_config.split('-') if seat_config else []
        if len(parts) == 2:
            config_rows = int(parts[0])
            config_cols = int(parts[1])
        else:
            config_cols = 4

        total_seats = aircraft.TotalSeats if aircraft else 180
        seats_per_row = config_cols
        num_rows = total_seats // seats_per_row + (1 if total_seats % seats_per_row > 0 else 0)

        for number, seat_class in seat_list(total_seats):
            db.session.add(Seat(FlightID=flight.FlightID, SeatNumber=number,
                                Class=seat_class, IsAvailable=True))

        db.session.commit()
        flash('Flight added successfully with seats', 'success')
        return redirect(url_for('admin_dashboard'))

    fare_classes = FareClass.query.filter_by(Active=True).order_by(FareClass.Multiplier).all()
    return render_template('admin_add_flight.html', routes=routes, fare_classes=fare_classes, aircrafts=Aircraft.query.order_by(Aircraft.RegistrationNumber).all())


@app.route('/admin/manage-users', methods=['GET', 'POST'])
def admin_manage_users():
    """Manage login accounts and employee job titles."""
    positions = {
        'operations', 'maintenance_technician', 'maintenance_supervisor', 'cleaner',
        'check_in_agent', 'gate_agent', 'baggage_handler', 'ground_staff', 'crew_scheduler',
        'dispatcher', 'staff'
    }
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        role = request.form.get('role', 'staff')
        name = (request.form.get('name') or '').strip()
        position = (request.form.get('position') or 'staff').strip().lower()
        if not username or len(password) < 8 or role not in {'staff', 'admin'}:
            flash('Enter a username, a password of at least 8 characters, and a valid role', 'error')
            return redirect(request.url)
        if role == 'staff' and position not in positions:
            flash('Choose a valid employee job title.', 'error')
            return redirect(request.url)
        existing = UserAccount.query.filter_by(Username=username).first()
        if existing:
            flash('Username already exists', 'error')
            return redirect(request.url)
        user = UserAccount(Username=username, Password=hash_password(password), Role=role)
        db.session.add(user)
        db.session.flush()
        employee = Employee(
            UserID=user.UserID, Name=name or ('Admin' if role == 'admin' else 'Staff Member'),
            Position='admin' if role == 'admin' else position,
            PhoneExtension='5000' if role == 'admin' else str(random.randint(5000, 5999))
        )
        db.session.add(employee)
        db.session.flush()
        _audit('create_user', 'UserAccount', user.UserID, f'role={role}; position={employee.Position}')
        db.session.commit()
        flash('User created successfully', 'success')
        return redirect(url_for('admin_manage_users'))
    users = UserAccount.query.order_by(UserAccount.Role, UserAccount.Username).all()
    employees_by_user = {e.UserID: e for e in Employee.query.all()}
    return render_template('admin_manage_users.html', users=users, employees_by_user=employees_by_user)


@app.route('/admin/reports', methods=['GET'])
def admin_reports():
    """Date-filtered revenue and occupancy report; CSV export uses the same filters."""
    from datetime import date
    start_text = (request.args.get('start_date') or '').strip()
    end_text = (request.args.get('end_date') or '').strip()
    status = (request.args.get('status') or '').strip().lower()
    start_date = end_date = None
    try:
        start_date = date.fromisoformat(start_text) if start_text else None
        end_date = date.fromisoformat(end_text) if end_text else None
        if start_date and end_date and start_date > end_date:
            raise ValueError('start date after end date')
    except ValueError:
        flash('Invalid report date range.', 'error')
        start_date = end_date = None
        start_text = end_text = ''
    flights_query = Flight.query
    if start_date:
        flights_query = flights_query.filter(Flight.DepartureTime >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        flights_query = flights_query.filter(Flight.DepartureTime < datetime.combine(end_date + timedelta(days=1), datetime.min.time()))
    if status in {'on_time', 'delayed', 'cancelled', 'completed', 'departed', 'arrived'}:
        flights_query = flights_query.filter(Flight.Status == status)
    flights = flights_query.order_by(Flight.DepartureTime.desc()).limit(500).all()
    flight_ids = [f.FlightID for f in flights]
    seat_counts = dict(db.session.query(Seat.FlightID, db.func.count(Seat.SeatID))
        .filter(Seat.FlightID.in_(flight_ids)).group_by(Seat.FlightID).all()) if flight_ids else {}
    booking_counts = dict(db.session.query(Booking.FlightID, db.func.coalesce(db.func.sum(Booking.NumberOfSeats), 0))
        .filter(Booking.FlightID.in_(flight_ids), Booking.Status == 'confirmed').group_by(Booking.FlightID).all()) if flight_ids else {}
    revenue_counts = dict(db.session.query(Ticket.FlightID, db.func.coalesce(db.func.sum(Ticket.FarePaid), 0))
        .filter(Ticket.FlightID.in_(flight_ids), Ticket.Status == 'issued').group_by(Ticket.FlightID).all()) if flight_ids else {}
    flight_occupancy = []
    for flight in flights:
        total_seats = seat_counts.get(flight.FlightID, 0)
        booked_seats = int(booking_counts.get(flight.FlightID, 0) or 0)
        revenue = float(revenue_counts.get(flight.FlightID, 0) or 0)
        occupancy_rate = (booked_seats / total_seats * 100) if total_seats else 0
        flight_occupancy.append({'flight': flight, 'total_seats': total_seats, 'booked': booked_seats,
                                 'occupancy_rate': round(occupancy_rate, 1), 'revenue': round(revenue, 2)})
    dep = db.aliased(Airport)
    arr = db.aliased(Airport)
    revenue_query = db.session.query(
        Route.RouteID, (dep.Code + ' - ' + arr.Code).label('route_name'),
        db.func.sum(Ticket.FarePaid).label('revenue')
    ).join(Flight, Flight.RouteID == Route.RouteID).join(dep, Route.DepartureAirportID == dep.AirportID) \
     .join(arr, Route.ArrivalAirportID == arr.AirportID).join(Ticket, Ticket.FlightID == Flight.FlightID)
    if start_date:
        revenue_query = revenue_query.filter(Flight.DepartureTime >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        revenue_query = revenue_query.filter(Flight.DepartureTime < datetime.combine(end_date + timedelta(days=1), datetime.min.time()))
    if status in {'on_time', 'delayed', 'cancelled', 'completed', 'departed', 'arrived'}:
        revenue_query = revenue_query.filter(Flight.Status == status)
    revenue_per_route = revenue_query.group_by(Route.RouteID, dep.Code, arr.Code).all()
    if request.args.get('format') == 'csv':
        import csv, io
        from flask import make_response
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Flight', 'Departure', 'Arrival', 'Status', 'Total seats', 'Confirmed seats', 'Occupancy %', 'Ticket revenue'])
        for item in flight_occupancy:
            f = item['flight']
            writer.writerow([f.FlightNumber, f.DepartureTime.isoformat(), f.ArrivalTime.isoformat(), f.Status,
                             item['total_seats'], item['booked'], item['occupancy_rate'], item['revenue']])
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = 'attachment; filename="aerion-report.csv"'
        _audit('export_reports_csv', 'Report', details=f'{len(flight_occupancy)} flight rows')
        db.session.commit()
        return response
    loyalty_accounts = LoyaltyAccount.query.all()
    total_miles = sum(a.MilesBalance for a in loyalty_accounts)
    avg_miles = total_miles / len(loyalty_accounts) if loyalty_accounts else 0
    recent_activity = Booking.query.order_by(Booking.BookingDate.desc()).limit(10).all()
    _audit('view_reports', 'Report', details=f'filters: start={start_text}, end={end_text}, status={status or "all"}')
    db.session.commit()
    return render_template('admin_reports.html', revenue_per_route=revenue_per_route,
        flight_occupancy=flight_occupancy, total_miles=total_miles, avg_miles=round(avg_miles, 1),
        recent_activity=recent_activity, start_date=start_text, end_date=end_text, selected_status=status)


def _current_user_account():
    """Resolve the signed-in user from the session's role-specific entity ID."""
    admin_id = session.get('admin_id')
    if admin_id:
        return db.session.get(UserAccount, admin_id)
    staff_id = session.get('staff_id')
    if staff_id:
        employee = db.session.get(Employee, staff_id)
        return db.session.get(UserAccount, employee.UserID) if employee else None
    passenger_id = session.get('passenger_id')
    if passenger_id:
        passenger = db.session.get(Passenger, passenger_id)
        return db.session.get(UserAccount, passenger.UserID) if passenger else None
    return None

def _audit(action, entity_type, entity_id=None, details=None):
    """Append a small, non-secret audit record to the database session."""
    user = _current_user_account()
    db.session.add(AuditLog(
        ActorUserID=user.UserID if user else None,
        ActorUsername=user.Username if user else 'system',
        Action=str(action)[:100], EntityType=str(entity_type)[:80],
        EntityID=str(entity_id)[:80] if entity_id is not None else None,
        Details=str(details or '')[:2000]
    ))

@app.route('/admin/operations')
def admin_operations():
    flights = Flight.query.order_by(Flight.DepartureTime.desc()).limit(100).all()
    routes = Route.query.order_by(Route.RouteID).all()
    return render_template('admin_operations.html', flights=flights, routes=routes)

@app.route('/admin/activity-history')
def admin_activity_history():
    logs = AuditLog.query.order_by(AuditLog.CreatedAt.desc()).limit(300).all()
    return render_template('admin_activity_history.html', logs=logs)

@app.route('/admin/integrity')
def admin_integrity():
    issues = []
    seat_counts = dict(db.session.query(Seat.FlightID, db.func.count(Seat.SeatID))
                       .group_by(Seat.FlightID).all())
    for flight in Flight.query.order_by(Flight.DepartureTime).all():
        aircraft = db.session.get(Aircraft, flight.AircraftID) if flight.AircraftID else None
        route = db.session.get(Route, flight.RouteID) if flight.RouteID else None
        seat_count = seat_counts.get(flight.FlightID, 0)
        if flight.DepartureTime >= flight.ArrivalTime:
            issues.append(('critical', 'Invalid flight time range', f'{flight.FlightNumber} (ID {flight.FlightID})'))
        if not aircraft or not route:
            issues.append(('critical', 'Flight has missing aircraft or route', f'{flight.FlightNumber} (ID {flight.FlightID})'))
        elif seat_count > aircraft.TotalSeats:
            issues.append(('critical', 'Seat inventory exceeds aircraft capacity', f'{flight.FlightNumber}: {seat_count} seats vs {aircraft.TotalSeats}'))
        elif seat_count < aircraft.TotalSeats and flight.Status.lower() not in {'cancelled', 'completed'}:
            issues.append(('warning', 'Seat inventory is below aircraft capacity', f'{flight.FlightNumber}: {seat_count} seats vs {aircraft.TotalSeats}'))
    blocked_aircraft_ids = set(
        x[0] for x in db.session.query(AircraftDefect.AircraftID).filter(
            AircraftDefect.Severity == 'critical', AircraftDefect.Status != 'cleared'
        ).all()
    )
    blocked_aircraft_ids.update(
        x[0] for x in db.session.query(MaintenanceWorkOrder.AircraftID).filter(
            MaintenanceWorkOrder.Severity == 'critical', MaintenanceWorkOrder.Status != 'completed'
        ).all()
    )
    for aircraft_id in blocked_aircraft_ids:
        aircraft = db.session.get(Aircraft, aircraft_id)
        issues.append(('critical', 'Aircraft has unresolved critical maintenance', f'{aircraft.RegistrationNumber if aircraft else aircraft_id} must be blocked from service'))
    other_flight = db.aliased(Flight)
    overlaps = db.session.query(Flight, other_flight).filter(
        Flight.FlightID < other_flight.FlightID,
        Flight.AircraftID == other_flight.AircraftID,
        Flight.Status.notin_(['cancelled', 'completed']),
        other_flight.Status.notin_(['cancelled', 'completed']),
        Flight.DepartureTime < other_flight.ArrivalTime,
        other_flight.DepartureTime < Flight.ArrivalTime
    ).limit(500).all()
    for left, right in overlaps:
        issues.append(('critical', 'Aircraft assigned to overlapping flights', f'{left.FlightNumber} overlaps {right.FlightNumber}'))
    overbooked = db.session.query(Booking.FlightID, db.func.sum(Booking.NumberOfSeats)).filter(
        Booking.Status == 'confirmed'
    ).group_by(Booking.FlightID).all()
    for flight_id, booked in overbooked:
        total = seat_counts.get(flight_id, 0)
        if total and booked > total:
            f = db.session.get(Flight, flight_id)
            issues.append(('critical', 'Confirmed bookings exceed seat inventory', f'{f.FlightNumber if f else flight_id}: {booked}/{total}'))
    _audit('view_integrity_monitor', 'IntegrityMonitor', details=f'{len(issues)} issue(s) detected')
    db.session.commit()
    return render_template('admin_integrity.html', issues=issues)

@app.route('/admin/passenger-manifest/<int:flight_id>')
def admin_passenger_manifest(flight_id):
    flight = db.get_or_404(Flight, flight_id)
    rows = db.session.query(Booking, Passenger, Ticket).join(
        Passenger, Booking.PassengerID == Passenger.PassengerID
    ).outerjoin(Ticket, Ticket.BookingID == Booking.BookingID).filter(
        Booking.FlightID == flight_id, Booking.Status == 'confirmed'
    ).order_by(Passenger.Name, Ticket.SeatNumber).all()
    if request.args.get('format') == 'csv':
        import csv, io
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(['Flight', 'Passenger', 'Passport', 'Contact', 'Booking ID', 'Seat', 'Booking Status', 'Fare'])
        for booking, passenger, ticket in rows:
            writer.writerow([flight.FlightNumber, passenger.Name, passenger.PassportNumber, passenger.ContactInfo or '',
                             booking.BookingID, ticket.SeatNumber if ticket else '', booking.Status,
                             ticket.FarePaid if ticket else booking.TotalAmount])
        from flask import make_response
        response = make_response(out.getvalue())
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename="manifest-{flight.FlightNumber}.csv"'
        _audit('export_passenger_manifest', 'Flight', flight.FlightID, f'{len(rows)} booking row(s)')
        db.session.commit()
        return response
    _audit('view_passenger_manifest', 'Flight', flight.FlightID, f'{len(rows)} booking row(s)')
    db.session.commit()
    return render_template('admin_passenger_manifest.html', flight=flight, rows=rows)

@app.route('/admin/fare-classes', methods=['GET', 'POST'])
def admin_fare_classes():
    if request.method == 'POST':
        code = (request.form.get('code') or '').strip().lower()
        name = (request.form.get('name') or '').strip()
        multiplier = request.form.get('multiplier', type=float)
        if not code or not name or len(code) > 30 or multiplier is None or not (0.1 <= multiplier <= 10):
            flash('Enter a code, name, and a multiplier between 0.1 and 10.', 'error')
            return redirect(request.url)
        if FareClass.query.filter_by(Code=code).first():
            flash('That fare-class code already exists.', 'error')
            return redirect(request.url)
        fare = FareClass(Code=code, Name=name, Multiplier=multiplier, Active=True)
        db.session.add(fare)
        db.session.flush()
        _audit('create_fare_class', 'FareClass', fare.FareClassID, f'{code} x{multiplier}')
        db.session.commit()
        flash('Fare class added.', 'success')
        return redirect(url_for('admin_fare_classes'))
    if FareClass.query.count() == 0:
        db.session.add_all([
            FareClass(Code='economy', Name='Economy', Multiplier=1.0),
            FareClass(Code='premium_economy', Name='Premium Economy', Multiplier=1.45),
            FareClass(Code='business', Name='Business', Multiplier=2.8),
            FareClass(Code='first', Name='First Class', Multiplier=4.5)
        ])
        db.session.commit()
    fares = FareClass.query.order_by(FareClass.Multiplier).all()
    return render_template('admin_fare_classes.html', fares=fares)

@app.route('/admin/saved-filters', methods=['GET', 'POST'])
def admin_saved_filters():
    user = _current_user_account()
    if not user:
        flash('Please sign in again.', 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        query_string = (request.form.get('query_string') or '').strip()
        if not name or len(name) > 80 or len(query_string) > 1000:
            flash('Enter a filter name (max 80 characters).', 'error')
            return redirect(request.url)
        item = SavedFilter(UserID=user.UserID, Name=name, QueryString=query_string)
        db.session.add(item)
        try:
            db.session.flush()
            _audit('save_filter', 'SavedFilter', item.FilterID, name)
            db.session.commit()
            flash('Filter saved.', 'success')
        except Exception:
            db.session.rollback()
            flash('A filter with that name may already exist for your account.', 'error')
        return redirect(url_for('admin_saved_filters'))
    filters = SavedFilter.query.filter_by(UserID=user.UserID).order_by(SavedFilter.Name).all()
    return render_template('admin_saved_filters.html', filters=filters)

@app.route('/admin/saved-filters/<int:filter_id>/delete', methods=['POST'])
def admin_delete_saved_filter(filter_id):
    user = _current_user_account()
    item = db.get_or_404(SavedFilter, filter_id)
    if not user or item.UserID != user.UserID:
        return 'Forbidden', 403
    _audit('delete_saved_filter', 'SavedFilter', item.FilterID, item.Name)
    db.session.delete(item)
    db.session.commit()
    flash('Saved filter deleted.', 'success')
    return redirect(url_for('admin_saved_filters'))

@app.route('/admin/import-csv', methods=['GET', 'POST'])
def admin_import_csv():
    result = None
    if request.method == 'POST':
        upload = request.files.get('file')
        if not upload or not upload.filename or not upload.filename.lower().endswith('.csv'):
            flash('Upload a .csv file.', 'error')
            return redirect(request.url)
        raw = upload.stream.read(2_000_001)
        if len(raw) > 2_000_000:
            flash('CSV file is too large (maximum 2 MB).', 'error')
            return redirect(request.url)
        import csv, io
        try:
            reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
            required = {'FlightNumber','RouteID','AircraftID','DepartureTime','ArrivalTime','Status','FareClass'}
            if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                raise ValueError('CSV headers must be: ' + ', '.join(sorted(required)))
            rows = list(reader)
            if len(rows) > 500:
                raise ValueError('Maximum 500 rows per import.')
            valid, errors = [], []
            seen_numbers = set()
            pending_by_aircraft = {}
            for row_no, row in enumerate(rows, start=2):
                try:
                    number = (row.get('FlightNumber') or '').strip().upper()
                    route_id, aircraft_id = int(row['RouteID']), int(row['AircraftID'])
                    dep, arr = datetime.fromisoformat(row['DepartureTime']), datetime.fromisoformat(row['ArrivalTime'])
                    status = (row['Status'] or '').strip().lower()
                    fare = (row['FareClass'] or '').strip().lower()
                    if not number or len(number) > 10 or status not in {'on_time','delayed','cancelled'} or fare not in {'economy','premium_economy','business','first'}:
                        raise ValueError('invalid flight number, status or fare class')
                    if dep >= arr: raise ValueError('arrival must be later than departure')
                    if number in seen_numbers or Flight.query.filter_by(FlightNumber=number).first():
                        raise ValueError('duplicate flight number')
                    route, aircraft = db.session.get(Route, route_id), db.session.get(Aircraft, aircraft_id)
                    if not route or not aircraft: raise ValueError('RouteID or AircraftID does not exist')
                    overlap = Flight.query.filter(
                        Flight.AircraftID == aircraft_id,
                        Flight.Status.notin_(['cancelled','completed']),
                        Flight.DepartureTime < arr, Flight.ArrivalTime > dep
                    ).first()
                    if overlap: raise ValueError(f'aircraft overlaps flight {overlap.FlightNumber}')
                    for pending_dep, pending_arr, pending_number in pending_by_aircraft.get(aircraft_id, []):
                        if dep < pending_arr and arr > pending_dep:
                            raise ValueError(f'aircraft overlaps CSV row flight {pending_number}')
                    pending_by_aircraft.setdefault(aircraft_id, []).append((dep, arr, number))
                    seen_numbers.add(number)
                    valid.append((number, route_id, aircraft_id, dep, arr, status, fare, aircraft))
                except Exception as exc:
                    errors.append(f'Row {row_no}: {exc}')
            if errors:
                result = {'imported': 0, 'rejected': len(errors), 'errors': errors, 'validated': len(valid)}
                flash('No rows were imported because validation found errors. Fix the CSV and retry.', 'error')
            else:
                batch = ImportBatch(FileName=upload.filename[:255], TotalRows=len(rows), ImportedRows=len(valid),
                                    RejectedRows=0, Status='imported')
                user = _current_user_account()
                batch.UploadedByUserID = user.UserID if user else None
                db.session.add(batch)
                for number, route_id, aircraft_id, dep, arr, status, fare, aircraft in valid:
                    flight = Flight(RouteID=route_id, AircraftID=aircraft_id, FlightNumber=number,
                                    DepartureTime=dep, ArrivalTime=arr, Status=status, FareClass=fare)
                    db.session.add(flight)
                    db.session.flush()
                    for number, cls in seat_list(aircraft.TotalSeats):
                        db.session.add(Seat(FlightID=flight.FlightID, SeatNumber=number, Class=cls, IsAvailable=True))
                _audit('import_flights_csv', 'ImportBatch', details=f'{upload.filename}: {len(valid)} rows')
                db.session.commit()
                result = {'imported': len(valid), 'rejected': 0, 'errors': [], 'validated': len(valid)}
                flash(f'Imported {len(valid)} flights atomically.', 'success')
        except Exception as exc:
            db.session.rollback()
            result = {'imported': 0, 'rejected': 0, 'errors': [str(exc)], 'validated': 0}
            flash('CSV validation failed. No data was changed.', 'error')
    return render_template('admin_import_csv.html', result=result)

@app.route('/admin/routes/<int:route_id>/tracking')
def admin_route_tracking(route_id):
    route = db.get_or_404(Route, route_id)
    points = RouteWaypoint.query.filter_by(RouteID=route_id).order_by(RouteWaypoint.Sequence).all()
    airports = [db.session.get(Airport, route.DepartureAirportID), db.session.get(Airport, route.ArrivalAirportID)]
    # Seed a clearly labelled, deterministic illustrative route only when no simulation points exist.
    if not points and all(airports):
        airport_coords = {
            'CAI': (30.1219, 31.4056), 'LON': (51.4700, -0.4543),
            'PAR': (49.0097, 2.5479), 'NYC': (40.6413, -73.7781),
            'DUB': (53.4264, -6.2499), 'FRA': (50.0379, 8.5622),
            'DXB': (25.2532, 55.3657), 'AMS': (52.3105, 4.7683),
            'IST': (41.2753, 28.7519), 'BCN': (41.2974, 2.0833)
        }
        start_xy = airport_coords.get(airports[0].Code.upper(), (0.0, 0.0))
        end_xy = airport_coords.get(airports[1].Code.upper(), (0.0, 0.0))
        defaults = [
            ('Departure', start_xy[0], start_xy[1], 0, 0, airports[0].AirportID),
            ('Cruise waypoint A', start_xy[0] + (end_xy[0]-start_xy[0])*0.33,
             start_xy[1] + (end_xy[1]-start_xy[1])*0.33, 30000, 450, None),
            ('Cruise waypoint B', start_xy[0] + (end_xy[0]-start_xy[0])*0.66,
             start_xy[1] + (end_xy[1]-start_xy[1])*0.66, 34000, 460, None),
            ('Arrival', end_xy[0], end_xy[1], 0, 0, airports[1].AirportID)
        ]
        for seq, (label, lat, lon, alt, speed, stop_id) in enumerate(defaults, start=1):
            db.session.add(RouteWaypoint(RouteID=route.RouteID, Sequence=seq, Label=label, Latitude=lat,
                                         Longitude=lon, PlannedAltitudeFt=alt, PlannedSpeedKts=speed,
                                         StopAirportID=stop_id))
        db.session.commit()
        points = RouteWaypoint.query.filter_by(RouteID=route_id).order_by(RouteWaypoint.Sequence).all()
    _audit('view_simulated_route', 'Route', route.RouteID, 'Illustrative simulation; no live radar/feed connection')
    db.session.commit()
    points_data = [{'label': p.Label, 'lat': p.Latitude, 'lon': p.Longitude,
                    'altitude': p.PlannedAltitudeFt, 'speed': p.PlannedSpeedKts} for p in points]
    return render_template('admin_route_tracking.html', route=route, points=points,
                           points_data=points_data, simulated=True)

@app.route('/admin/routes/<int:route_id>/tracking/add-point', methods=['POST'])
def admin_add_route_point(route_id):
    route = db.get_or_404(Route, route_id)
    label = (request.form.get('label') or '').strip()
    lat, lon = request.form.get('latitude', type=float), request.form.get('longitude', type=float)
    alt, speed = request.form.get('altitude', type=int), request.form.get('speed', type=int)
    if not label or len(label) > 100 or lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180) or alt is None or not (0 <= alt <= 60000) or speed is None or not (0 <= speed <= 700):
        flash('Check waypoint name, coordinates, altitude (0–60,000 ft) and speed (0–700 kt).', 'error')
        return redirect(url_for('admin_route_tracking', route_id=route_id))
    seq = (db.session.query(db.func.max(RouteWaypoint.Sequence)).filter_by(RouteID=route_id).scalar() or 0) + 1
    point = RouteWaypoint(RouteID=route_id, Sequence=seq, Label=label, Latitude=lat, Longitude=lon,
                          PlannedAltitudeFt=alt, PlannedSpeedKts=speed)
    db.session.add(point)
    db.session.flush()
    _audit('add_route_waypoint', 'RouteWaypoint', point.WaypointID, f'{label} ({lat},{lon})')
    db.session.commit()
    return redirect(url_for('admin_route_tracking', route_id=route_id))

@app.after_request
def record_auditable_post(response):
    if request.method == 'POST' and response.status_code < 400 and request.endpoint not in {'login', 'register', 'logout'}:
        try:
            user = _current_user_account()
            if user:
                excluded = {'password', 'confirm_password', 'csrf_token', 'secret', 'token',
                            'passport', 'contact', 'email', 'phone', 'authorization'}
                safe_values = []
                for key in sorted(request.form.keys()):
                    if key.lower() in excluded or any(term in key.lower() for term in ('password', 'token', 'passport', 'contact', 'email', 'phone')):
                        continue
                    value = (request.form.get(key) or '').strip().replace('\\n', ' ')[:120]
                    if value:
                        safe_values.append(f'{key}={value}')
                db.session.add(AuditLog(ActorUserID=user.UserID, ActorUsername=user.Username,
                    Action=(request.endpoint or request.path)[:100], EntityType='HTTP operation',
                    EntityID=None, Details='Changed fields: ' + '; '.join(safe_values)))
                db.session.commit()
        except Exception:
            db.session.rollback()
    return response


# ========================================
# ERROR HANDLERS
# ========================================

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500


# ========================================
# RUN THE APP
# ========================================

@app.route('/employee-shifts', methods=['GET', 'POST'])
def admin_employee_shifts():
    """Manage employee shifts."""
    if request.method == 'POST':
        employee_id = request.form.get('employee_id', type=int)
        shift_type = request.form.get('shift_type')
        date_str = request.form.get('date')
        employee = db.session.get(Employee, employee_id) if employee_id else None
        if not employee or shift_type not in {'morning', 'afternoon', 'night'} or not date_str:
            flash('Choose a valid employee, shift, and date', 'error')
            return redirect(request.url)
        try:
            date = datetime.fromisoformat(date_str)
        except ValueError:
            flash('Enter a valid shift date', 'error')
            return redirect(request.url)
        shift = EmployeeShift(
            EmployeeID=employee_id,
            Date=date,
            ShiftType=shift_type,
            Status='assigned'
        )
        db.session.add(shift)
        db.session.commit()
        flash('Shift assigned successfully', 'success')
        return redirect(url_for('admin_employee_shifts'))

    shifts = EmployeeShift.query.order_by(EmployeeShift.Date.desc()).all()
    employees = Employee.query.all()
    return render_template('admin_employee_shifts.html', shifts=shifts, employees=employees)


@app.route('/employee-qualifications', methods=['GET', 'POST'])
def admin_employee_qualifications():
    """Manage employee qualifications."""
    if request.method == 'POST':
        employee_id = request.form.get('employee_id', type=int)
        qual_name = (request.form.get('qualification_name') or '').strip()
        aircraft_type = (request.form.get('aircraft_type') or '').strip()
        if not employee_id or not db.session.get(Employee, employee_id) or not qual_name:
            flash('Choose a valid employee and enter a qualification', 'error')
            return redirect(request.url)
        qual = EmployeeQualification(
            EmployeeID=employee_id,
            QualificationName=qual_name,
            AuthorizedAircraftType=aircraft_type,
            IssuedDate=datetime.now(),
            ExpiryDate=None
        )
        db.session.add(qual)
        db.session.commit()
        flash('Qualification added successfully', 'success')
        return redirect(url_for('admin_employee_qualifications'))

    qualifications = EmployeeQualification.query.all()
    employees = Employee.query.all()
    return render_template('admin_employee_qualifications.html', qualifications=qualifications, employees=employees)


@app.route('/maintenance-work-orders', methods=['GET', 'POST'])
def admin_maintenance_work_orders():
    """Manage aircraft maintenance work orders."""
    maintenance_positions = {'maintenance_technician', 'maintenance_supervisor'}
    if request.method == 'POST':
        aircraft_id = request.form.get('aircraft_id', type=int)
        description = (request.form.get('description') or '').strip()
        severity = request.form.get('severity', 'minor')
        technician_id = request.form.get('technician_id', type=int)
        if not aircraft_id or not db.session.get(Aircraft, aircraft_id) or not description or len(description) > 200 or severity not in {'minor', 'major', 'critical'}:
            flash('Choose a valid aircraft and enter a description and severity', 'error')
            return redirect(request.url)
        technician = db.session.get(Employee, technician_id) if technician_id else None
        if technician_id and (not technician or technician.Position not in maintenance_positions):
            flash('Only a maintenance technician or supervisor can be assigned to a work order.', 'error')
            return redirect(request.url)
        work_order = MaintenanceWorkOrder(
            AircraftID=aircraft_id, Description=description, Severity=severity,
            Status='pending', AssignedTechnicianID=technician.EmployeeID if technician else None
        )
        db.session.add(work_order)
        db.session.flush()
        _audit('create_maintenance_work_order', 'MaintenanceWorkOrder', work_order.WorkOrderID,
               f'aircraft={aircraft_id}; severity={severity}; assigned={technician.Name if technician else "unassigned"}')
        db.session.commit()
        flash('Work order created successfully', 'success')
        return redirect(url_for('admin_maintenance_work_orders'))
    work_orders = MaintenanceWorkOrder.query.join(Aircraft).order_by(MaintenanceWorkOrder.ReportedDate.desc()).all()
    aircrafts = Aircraft.query.all()
    technicians = Employee.query.filter(Employee.Position.in_(list(maintenance_positions))).order_by(Employee.Name).all()
    return render_template('admin_maintenance_work_orders.html', work_orders=work_orders, aircrafts=aircrafts, technicians=technicians)


@app.route('/maintenance-work-orders/<int:work_order_id>/status', methods=['POST'])
def admin_update_work_order_status(work_order_id):
    item = db.get_or_404(MaintenanceWorkOrder, work_order_id)
    next_status = (request.form.get('status') or '').strip().lower()
    allowed = {'pending', 'in_progress', 'completed', 'blocked'}
    if next_status not in allowed:
        flash('Invalid work order status.', 'error')
        return redirect(url_for('admin_maintenance_work_orders'))
    if next_status == 'completed' and item.Severity == 'critical' and not item.AssignedTechnicianID:
        flash('Assign a maintenance technician before closing a critical work order.', 'error')
        return redirect(url_for('admin_maintenance_work_orders'))
    old_status = item.Status
    item.Status = next_status
    item.ResolvedDate = datetime.now(timezone.utc).replace(tzinfo=None) if next_status == 'completed' else None
    _audit('update_work_order_status', 'MaintenanceWorkOrder', item.WorkOrderID, f'{old_status} -> {next_status}')
    db.session.commit()
    flash('Work order status updated.', 'success')
    return redirect(url_for('admin_maintenance_work_orders'))

@app.route('/aircraft-defects', methods=['GET', 'POST'])
def admin_aircraft_defects():
    """Manage aircraft defects."""
    if request.method == 'POST':
        aircraft_id = request.form.get('aircraft_id', type=int)
        description = (request.form.get('description') or '').strip()
        severity = request.form.get('severity', 'minor')
        if not aircraft_id or not db.session.get(Aircraft, aircraft_id) or not description or severity not in {'minor', 'major', 'critical'}:
            flash('Choose a valid aircraft and enter a description and severity', 'error')
            return redirect(request.url)
        defect = AircraftDefect(
            AircraftID=aircraft_id,
            Description=description,
            Severity=severity,
            Status='reported'
        )
        db.session.add(defect)
        db.session.commit()
        flash('Defect recorded successfully', 'success')
        return redirect(url_for('admin_aircraft_defects'))

    defects = AircraftDefect.query.join(Aircraft).order_by(AircraftDefect.ReportedDate.desc()).limit(20).all()
    aircrafts = Aircraft.query.all()
    return render_template('admin_aircraft_defects.html', defects=defects, aircrafts=aircrafts)




@app.route('/aircraft-defects/<int:defect_id>/status', methods=['POST'])
def admin_update_aircraft_defect_status(defect_id):
    item = db.get_or_404(AircraftDefect, defect_id)
    next_status = (request.form.get('status') or '').strip().lower()
    allowed = {'reported', 'under_repair', 'cleared'}
    if next_status not in allowed:
        flash('Invalid defect status.', 'error')
        return redirect(url_for('admin_aircraft_defects'))
    old_status = item.Status
    item.Status = next_status
    item.ResolvedDate = datetime.now(timezone.utc).replace(tzinfo=None) if next_status == 'cleared' else None
    _audit('update_aircraft_defect_status', 'AircraftDefect', item.DefectID, f'{old_status} -> {next_status}')
    db.session.commit()
    flash('Aircraft defect status updated.', 'success')
    return redirect(url_for('admin_aircraft_defects'))

@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    flash("You have been logged out", "success")
    return redirect(url_for("index"))


if __name__ == '__main__':
    init_database()
    app.run(
        host=os.environ.get('HOST', '127.0.0.1'),
        port=int(os.environ.get('PORT', '5000')),
        debug=os.environ.get('FLASK_DEBUG', '0').lower() in {'1', 'true', 'yes'}
    )
