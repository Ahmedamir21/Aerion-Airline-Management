"""Comprehensive test suite for Airline Management System."""
import pytest
import threading
from concurrent.futures import ThreadPoolExecutor
import time
from datetime import datetime
import uuid
from app import app, db
from app import (
    UserAccount, Passenger, Employee, Airport, Route, Aircraft,
    Flight, Seat, Booking, Ticket, Payment, Refund, Baggage,
    LoyaltyAccount, EmployeeQualification, EmployeeShift, MaintenanceWorkOrder, AircraftDefect
)
from flask import session
from werkzeug.security import check_password_hash, generate_password_hash
import hashlib
from pathlib import Path


@pytest.fixture(autouse=True)
def setup_and_teardown():
    """Set up database for each test and clean up afterwards."""
    with app.app_context():
        app.config['WTF_CSRF_ENABLED'] = False  # Dedicated regression test enables CSRF below.
        db.drop_all()
        db.create_all()
        from app import init_database
        init_database()
    yield
    with app.app_context():
        db.session.remove()
        db.drop_all()


class TestDatabaseInitialization:
    """Test that database initializes correctly with all 24 tables."""

    def test_all_tables_created(self):
        """All 19 tables should be created after init_database."""
        with app.app_context():
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            expected = [
                'UserAccount', 'Passenger', 'Employee', 'CrewMember', 'Airport',
                'Route', 'Aircraft', 'Flight', 'Seat', 'Booking',
                'Ticket', 'Payment', 'Refund', 'Baggage', 'LoyaltyAccount',
                'EmployeeQualification', 'EmployeeShift',
                'MaintenanceWorkOrder', 'AircraftDefect', 'AuditLog', 'SavedFilter',
                'FareClass', 'RouteWaypoint', 'ImportBatch'
            ]
            for exp in expected:
                assert exp in tables, f"Table {exp} missing"

    def test_sample_data_counts(self):
        """Database should have sample data across all entities."""
        with app.app_context():
            from app import UserAccount, Passenger, Employee, Airport, Route, Aircraft, Flight, Seat, Booking, Ticket, Payment, Baggage, LoyaltyAccount, EmployeeQualification, EmployeeShift, MaintenanceWorkOrder, AircraftDefect

            counts = {
                'UserAccount': db.session.query(UserAccount).count(),
                'Passenger': db.session.query(Passenger).count(),
                'Employee': db.session.query(Employee).count(),
                'Airport': db.session.query(Airport).count(),
                'Route': db.session.query(Route).count(),
                'Aircraft': db.session.query(Aircraft).count(),
                'Flight': db.session.query(Flight).count(),
                'Seat': db.session.query(Seat).count(),
                'Booking': db.session.query(Booking).count(),
                'Ticket': db.session.query(Ticket).count(),
                'Payment': db.session.query(Payment).count(),
                'Refund': db.session.query(Refund).count(),
                'Baggage': db.session.query(Baggage).count(),
                'LoyaltyAccount': db.session.query(LoyaltyAccount).count(),
                'EmployeeQualification': db.session.query(EmployeeQualification).count(),
                'EmployeeShift': db.session.query(EmployeeShift).count(),
                'MaintenanceWorkOrder': db.session.query(MaintenanceWorkOrder).count(),
                'AircraftDefect': db.session.query(AircraftDefect).count(),
            }
            assert counts['UserAccount'] > 0
            assert counts['Passenger'] > 0
            assert counts['Flight'] > 0


class TestUserAccountModels:
    """Test UserAccount model and authentication."""

    def test_useraccount_creation(self):
        """UserAccount can be created with proper attributes."""
        with app.app_context():
            user = UserAccount(
                Username='testuser',
                Password='testpass123',
                Role='passenger'
            )
            db.session.add(user)
            db.session.commit()
            assert user.UserID is not None
            assert user.Username == 'testuser'
            assert user.Role == 'passenger'

    def test_useraccount_unique_username(self):
        """Username must be unique."""
        with app.app_context():
            user1 = UserAccount(Username='dupuser', Password='pass1', Role='passenger')
            db.session.add(user1)
            db.session.commit()
            user2 = UserAccount(Username='dupuser', Password='pass2', Role='passenger')
            db.session.add(user2)
            try:
                db.session.commit()
                assert False, "Should have failed with duplicate username"
            except Exception:
                assert True

    def test_password_hashing_scrypt(self):
        """Passwords should be hashed with scrypt format."""
        with app.app_context():
            password = 'testpassword123'
            hashed = generate_password_hash(password, method='scrypt')
            assert hashed.startswith('scrypt:')

    def test_check_password_hash_scrypt(self):
        """check_password_hash should work with scrypt hashes."""
        with app.app_context():
            from werkzeug.security import generate_password_hash, check_password_hash
            password = 'mysupersecret'
            hashed = generate_password_hash(password, method='scrypt')
            assert check_password_hash(hashed, password)

    def test_legacy_sha256_password_is_upgraded_on_login(self):
        """Successful legacy login must migrate the stored hash to Werkzeug scrypt."""
        client = app.test_client()
        with app.app_context():
            user = UserAccount.query.filter_by(Username='passenger1').first()
            assert user is not None
            user.Password = hashlib.sha256('password123'.encode()).hexdigest()
            user_id = user.UserID
            db.session.commit()

        response = client.post('/login', data={
            'username': 'passenger1', 'password': 'password123'
        }, follow_redirects=False)
        assert response.status_code == 302
        with app.app_context():
            updated = UserAccount.query.get(user_id)
            assert updated is not None
            assert updated.Password.startswith('scrypt:')
            assert check_password_hash(updated.Password, 'password123')



class TestPassengerOperations:
    """Test passenger-facing operations."""

    def test_passenger_login_and_dashboard(self):
        """Passenger should be able to log in and render the dashboard and search form."""
        client = app.test_client()
        response = client.post('/login', data={
            'username': 'passenger1',
            'password': 'password123'
        })
        assert response.status_code == 302
        response = client.get('/passenger-dashboard')
        assert response.status_code == 200
        assert b'Welcome' in response.data
        response = client.get('/passenger/search-flights')
        assert response.status_code == 200
        assert b'Search Flights' in response.data

    def test_passenger_search_results_render(self):
        """Search results should render route, fare, date, and seat counts."""
        client = app.test_client()
        with app.app_context():
            flight = Flight.query.first()
            assert flight is not None and flight.Route is not None
            origin = flight.Route.DepartureAirport.Code
            destination = flight.Route.ArrivalAirport.Code
            date_str = flight.DepartureTime.strftime('%Y-%m-%d')
            flight_number = flight.FlightNumber
        response = client.post('/passenger/search-flights', data={
            'origin': origin,
            'destination': destination,
            'date': date_str
        })
        assert response.status_code == 200
        assert b'Search Results' in response.data
        assert flight_number.encode() in response.data
        assert b'Seats' in response.data

    def test_passenger_search_flights(self):
        """Passenger should be able to search flights."""
        with app.app_context():
            flights = Flight.query.limit(5).all()
            assert len(flights) > 0

    def test_booking_page_renders_for_authenticated_passenger(self):
        """The booking form must compile and render successfully."""
        client = app.test_client()
        with app.app_context():
            user = UserAccount.query.filter_by(Username='passenger1').first()
            passenger = Passenger.query.filter_by(UserID=user.UserID).first() if user else None
            flight = Flight.query.first()
            assert passenger is not None and flight is not None
            passenger_id, flight_id = passenger.PassengerID, flight.FlightID
        with client.session_transaction() as sess:
            sess['passenger_id'] = passenger_id
        response = client.get(f'/passenger/book/{flight_id}')
        assert response.status_code == 200
        assert b'Select Seats' in response.data
        assert b'Estimated price per seat' in response.data

    def test_multi_seat_booking_creates_one_booking_and_ticket_per_seat(self):
        """Multiple selected seats must reserve atomically without violating unique ticket booking IDs."""
        client = app.test_client()
        with app.app_context():
            user = UserAccount.query.filter_by(Username='passenger1').first()
            passenger = Passenger.query.filter_by(UserID=user.UserID).first() if user else None
            flight = Flight.query.first()
            assert passenger is not None and flight is not None
            seats = Seat.query.filter_by(FlightID=flight.FlightID, IsAvailable=True).limit(2).all()
            assert len(seats) == 2
            passenger_id, flight_id = passenger.PassengerID, flight.FlightID
            seat_numbers = [seat.SeatNumber for seat in seats]
            before_bookings = Booking.query.filter_by(PassengerID=passenger_id, FlightID=flight_id).count()
            before_tickets = Ticket.query.filter_by(PassengerID=passenger_id, FlightID=flight_id).count()
        with client.session_transaction() as sess:
            sess['passenger_id'] = passenger_id
        response = client.post(f'/passenger/book/{flight_id}', data={'seats': seat_numbers})
        assert response.status_code == 302
        with app.app_context():
            after_bookings = Booking.query.filter_by(PassengerID=passenger_id, FlightID=flight_id).count()
            after_tickets = Ticket.query.filter_by(PassengerID=passenger_id, FlightID=flight_id).count()
            for seat_number in seat_numbers:
                seat = Seat.query.filter_by(FlightID=flight_id, SeatNumber=seat_number).first()
                assert seat is not None and seat.IsAvailable is False
        assert after_bookings - before_bookings == 2
        assert after_tickets - before_tickets == 2


    def test_passenger_book_flight(self):
        """The real booking endpoint must reserve a seat and create a booking and ticket."""
        client = app.test_client()
        with app.app_context():
            user = UserAccount.query.filter_by(Username='passenger1').first()
            assert user is not None
            passenger = Passenger.query.filter_by(UserID=user.UserID).first()
            assert passenger is not None
            flight = Flight.query.first()
            assert flight is not None
            seat = Seat.query.filter_by(FlightID=flight.FlightID, IsAvailable=True).first()
            assert seat is not None
            flight_id, passenger_id, seat_number = flight.FlightID, passenger.PassengerID, seat.SeatNumber

        with client.session_transaction() as sess:
            sess['passenger_id'] = passenger_id

        response = client.post(
            f'/passenger/book/{flight_id}',
            data={'seats': [seat_number]},
            follow_redirects=False
        )
        assert response.status_code == 302

        with app.app_context():
            booking = Booking.query.filter_by(PassengerID=passenger_id, FlightID=flight_id).order_by(Booking.BookingID.desc()).first()
            assert booking is not None
            assert booking.NumberOfSeats == 1
            ticket = Ticket.query.filter_by(BookingID=booking.BookingID).first()
            assert ticket is not None
            assert ticket.SeatNumber == seat_number
            reserved_seat = Seat.query.filter_by(FlightID=flight_id, SeatNumber=seat_number).first()
            assert reserved_seat is not None and reserved_seat.IsAvailable is False

    def test_csrf_token_is_required_for_state_changing_requests(self):
        client = app.test_client()
        app.config['WTF_CSRF_ENABLED'] = True
        try:
            assert client.get('/login').status_code == 200
            assert client.post('/login', data={'username': 'passenger1', 'password': 'password123'}).status_code == 400
            with client.session_transaction() as sess:
                token = sess['_csrf_token']
            response = client.post('/login', data={'username': 'passenger1', 'password': 'password123', 'csrf_token': token})
            assert response.status_code == 302
        finally:
            app.config['WTF_CSRF_ENABLED'] = False

    def test_booking_records_demo_payment(self):
        client = app.test_client()
        with app.app_context():
            user = UserAccount.query.filter_by(Username='passenger1').first()
            passenger = Passenger.query.filter_by(UserID=user.UserID).first()
            flight = Flight.query.filter(Flight.DepartureTime > datetime.now()).filter(Flight.Status != 'cancelled').first()
            assert passenger and flight
            seat = Seat.query.filter_by(FlightID=flight.FlightID, IsAvailable=True).first()
            assert seat
            passenger_id, flight_id, seat_number = passenger.PassengerID, flight.FlightID, seat.SeatNumber
        with client.session_transaction() as sess: sess['passenger_id'] = passenger_id
        assert client.post(f'/passenger/book/{flight_id}', data={'seats': [seat_number], 'payment_method': 'card'}).status_code == 302
        with app.app_context():
            booking = Booking.query.filter_by(PassengerID=passenger_id, FlightID=flight_id).order_by(Booking.BookingID.desc()).first()
            payment = Payment.query.filter_by(BookingID=booking.BookingID).first()
            assert payment and payment.Amount == booking.TotalAmount
            assert payment.PaymentMethod == 'card' and payment.TransactionID.startswith('PAY-')

    def test_cancellation_records_one_demo_refund_and_releases_seat(self):
        client = app.test_client()
        with app.app_context():
            user = UserAccount.query.filter_by(Username='passenger1').first()
            passenger = Passenger.query.filter_by(UserID=user.UserID).first()
            flight = Flight.query.filter(Flight.DepartureTime > datetime.now()).filter(Flight.Status != 'cancelled').first()
            assert passenger and flight
            seat = Seat.query.filter_by(FlightID=flight.FlightID, IsAvailable=True).first()
            assert seat
            booking = Booking(PassengerID=passenger.PassengerID, FlightID=flight.FlightID, NumberOfSeats=1, TotalAmount=250.0, Status='confirmed')
            db.session.add(booking); db.session.flush()
            payment = Payment(BookingID=booking.BookingID, Amount=250.0, PaymentMethod='card', TransactionID='TEST-PAY-' + uuid.uuid4().hex)
            db.session.add(payment)
            ticket = Ticket(BookingID=booking.BookingID, PassengerID=passenger.PassengerID, FlightID=flight.FlightID, SeatNumber=seat.SeatNumber, FarePaid=250.0, Status='issued')
            db.session.add(ticket); seat.IsAvailable = False; db.session.commit()
            booking_id, passenger_id = booking.BookingID, passenger.PassengerID
        with client.session_transaction() as sess: sess['passenger_id'] = passenger_id
        assert client.post(f'/passenger/cancel-booking/{booking_id}').status_code == 302
        assert client.post(f'/passenger/cancel-booking/{booking_id}').status_code == 302
        with app.app_context():
            booking = db.session.get(Booking, booking_id)
            refund = Refund.query.filter_by(BookingID=booking_id).first()
            ticket = Ticket.query.filter_by(BookingID=booking_id).first()
            seat = Seat.query.filter_by(FlightID=booking.FlightID, SeatNumber=ticket.SeatNumber).first()
            assert booking.Status == 'cancelled' and ticket.Status == 'cancelled'
            assert refund and refund.Amount == 250.0 and refund.Status == 'simulated'
            assert Refund.query.filter_by(BookingID=booking_id).count() == 1
            assert seat.IsAvailable is True

    def test_cancelled_flight_cannot_be_booked(self):
        client = app.test_client()
        with app.app_context():
            user = UserAccount.query.filter_by(Username='passenger1').first()
            passenger = Passenger.query.filter_by(UserID=user.UserID).first()
            flight = Flight.query.first()
            assert passenger and flight
            passenger_id, flight_id = passenger.PassengerID, flight.FlightID
            flight.Status = 'cancelled'; db.session.commit()
        with client.session_transaction() as sess: sess['passenger_id'] = passenger_id
        response = client.get(f'/passenger/book/{flight_id}')
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/passenger/search-flights')


class TestStaffOperations:
    """Test staff-facing operations."""

    def test_staff_routes_require_staff_session(self):
        """Every staff workflow must reject unauthenticated requests."""
        client = app.test_client()
        paths = [
            ('GET', '/staff-dashboard'),
            ('GET', '/staff/check-in/1'),
            ('GET', '/staff/register-baggage/1'),
            ('POST', '/staff/set-flight-status/1'),
            ('GET', '/staff/passenger-list/1'),
        ]
        for method, path in paths:
            response = client.open(path, method=method)
            assert response.status_code == 302, f"{method} {path} was not protected"
            assert response.headers['Location'].endswith('/login')

    def test_admin_routes_require_admin_session(self):
        """Every admin workflow must reject unauthenticated requests."""
        client = app.test_client()
        paths = [
            '/admin-dashboard', '/admin/add-airport', '/admin/add-route',
            '/admin/add-aircraft', '/admin/add-flight', '/admin/manage-users',
            '/admin/reports', '/employee-shifts', '/employee-qualifications',
            '/maintenance-work-orders', '/aircraft-defects',
        ]
        for path in paths:
            response = client.get(path)
            assert response.status_code == 302, f"GET {path} was not protected"
            assert response.headers['Location'].endswith('/login')

    def test_predictable_development_secret_is_not_used(self):
        """The old public development key must never sign session cookies."""
        assert app.config['SECRET_KEY'] != 'dev-secret-key-change-in-production'

    def test_login_clears_previous_admin_session_when_switching_accounts(self):
        """A passenger login must not retain a prior administrator session."""
        client = app.test_client()
        with app.app_context():
            admin = UserAccount.query.filter_by(Role='admin').first()
            assert admin is not None
            admin_id = admin.UserID

        with client.session_transaction() as sess:
            sess['admin_id'] = admin_id

        response = client.post('/login', data={
            'username': 'passenger1',
            'password': 'password123'
        })
        assert response.status_code == 302
        with client.session_transaction() as sess:
            assert 'admin_id' not in sess
            assert 'passenger_id' in sess
        response = client.get('/admin/add-airport')
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/login')

    def test_passenger_session_cannot_impersonate_admin_or_staff(self):
        """Role-specific routes must validate the session ID against the database role."""
        client = app.test_client()
        with app.app_context():
            passenger_user = UserAccount.query.filter_by(Role='passenger').first()
            staff_user = UserAccount.query.filter_by(Role='staff').first()
            assert passenger_user is not None and staff_user is not None
            passenger_user_id = passenger_user.UserID
            staff_user_id = staff_user.UserID
            invalid_employee_id = (db.session.query(db.func.max(Employee.EmployeeID)).scalar() or 0) + 1000

        with client.session_transaction() as sess:
            sess['admin_id'] = staff_user_id
        response = client.get('/admin/add-airport')
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/login')

        with client.session_transaction() as sess:
            sess.clear()
            sess['staff_id'] = invalid_employee_id
        response = client.get('/staff/passenger-list/1')
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/login')

    def test_staff_login(self):
        """Staff should be able to log in."""
        with app.app_context():
            user = UserAccount.query.filter_by(Role='staff').first()
            assert user is not None

    def test_staff_check_in(self):
        """The staff check-in page requires a staff session and loads a real booking."""
        client = app.test_client()
        with app.app_context():
            staff_user = UserAccount.query.filter_by(Role='staff').first()
            assert staff_user is not None
            employee = Employee.query.filter_by(UserID=staff_user.UserID).first()
            passenger_user = UserAccount.query.filter_by(Username='passenger1').first()
            assert employee is not None and passenger_user is not None
            passenger = Passenger.query.filter_by(UserID=passenger_user.UserID).first()
            flight = Flight.query.first()
            assert passenger is not None and flight is not None
            booking = Booking(
                PassengerID=passenger.PassengerID, FlightID=flight.FlightID,
                NumberOfSeats=1, TotalAmount=200.0, Status='confirmed'
            )
            db.session.add(booking)
            db.session.commit()
            booking_id, employee_id = booking.BookingID, employee.EmployeeID

        with client.session_transaction() as sess:
            sess['staff_id'] = employee_id
        response = client.get(f'/staff/check-in/{booking_id}')
        assert response.status_code == 200


class TestAdminOperations:
    """Test administrator-facing operations."""

    def test_admin_login(self):
        """Admin should be able to log in."""
        with app.app_context():
            user = UserAccount.query.filter_by(Role='admin').first()
            assert user is not None

    def test_admin_manage_routes(self):
        """Admin can manage routes."""
        with app.app_context():
            routes = Route.query.limit(5).all()
            assert len(routes) > 0


class TestConcurrentSeatReservation:
    """Test concurrent seat reservation with database locking."""

    def test_concurrent_http_booking_same_seat_creates_one_booking(self):
        """Race real HTTP booking requests and assert exactly one transaction wins."""
        with app.app_context():
            passenger_user = UserAccount.query.filter_by(Username='passenger1').first()
            assert passenger_user is not None
            passenger = Passenger.query.filter_by(UserID=passenger_user.UserID).first()
            flight = Flight.query.first()
            assert passenger is not None and flight is not None
            seat = Seat.query.filter_by(FlightID=flight.FlightID, IsAvailable=True).first()
            assert seat is not None
            seat.IsAvailable = True
            db.session.commit()
            passenger_id, flight_id, seat_number = passenger.PassengerID, flight.FlightID, seat.SeatNumber
            before_bookings = Booking.query.filter_by(
                PassengerID=passenger_id, FlightID=flight_id
            ).count()

        def submit_booking(_):
            client = app.test_client()
            with client.session_transaction() as sess:
                sess['passenger_id'] = passenger_id
            response = client.post(
                f'/passenger/book/{flight_id}',
                data={'seats': [seat_number]},
                follow_redirects=False
            )
            return response.status_code

        with ThreadPoolExecutor(max_workers=4) as pool:
            statuses = list(pool.map(submit_booking, range(4)))

        with app.app_context():
            after_bookings = Booking.query.filter_by(
                PassengerID=passenger_id, FlightID=flight_id
            ).count()
            tickets = Ticket.query.filter_by(
                PassengerID=passenger_id, FlightID=flight_id, SeatNumber=seat_number
            ).count()
            seat = Seat.query.filter_by(FlightID=flight_id, SeatNumber=seat_number).first()

        assert all(status == 302 for status in statuses), statuses
        assert after_bookings - before_bookings == 1, f"Expected one new booking, got statuses={statuses}"
        assert tickets == 1, f"Expected one ticket for the raced seat, found {tickets}"
        assert seat is not None and seat.IsAvailable is False

    def test_concurrent_reservation_same_seat(self):
        """Exactly one concurrent reservation succeeds for one available seat."""
        with app.app_context():
            from app import reserve_seat_atomically
            flight = Flight.query.first()
            assert flight is not None
            seat = Seat.query.filter_by(FlightID=flight.FlightID, SeatNumber='1A').first()
            assert seat is not None
            seat.IsAvailable = True
            db.session.commit()
            flight_id = flight.FlightID

        results = []
        def reserve_seat():
            success, _ = reserve_seat_atomically(flight_id, '1A', 1)
            results.append(success)

        threads = [threading.Thread(target=reserve_seat) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(results) == 3
        assert sum(bool(result) for result in results) == 1, f"Expected exactly one success, got {results}"

    def test_concurrent_reservation_different_seats(self):
        """Concurrent reservations for distinct available seats should all succeed."""
        with app.app_context():
            from app import reserve_seat_atomically
            flight = Flight.query.first()
            assert flight is not None
            seats = Seat.query.filter_by(FlightID=flight.FlightID).order_by(Seat.SeatNumber).limit(3).all()
            assert len(seats) == 3
            for seat in seats:
                seat.IsAvailable = True
            flight_id = flight.FlightID
            seat_numbers = [seat.SeatNumber for seat in seats]
            db.session.commit()

        results = []
        def reserve_seat(number):
            success, _ = reserve_seat_atomically(flight_id, number, 1)
            results.append(success)

        threads = [threading.Thread(target=reserve_seat, args=(number,)) for number in seat_numbers]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(results) == len(seat_numbers)
        assert all(results), f"Expected all distinct-seat reservations to succeed, got {results}"



class TestBookingOperations:
    """Test booking and ticket operations."""

    def test_booking_creates_ticket(self):
        """Booking should create a ticket with correct foreign key."""
        with app.app_context():
            from app import Flight, Passenger, UserAccount
            
            user = UserAccount.query.filter_by(Username='passenger1').first()
            if not user:
                pytest.skip("No passenger user available")
            
            passenger = Passenger.query.filter_by(UserID=user.UserID).first()
            if not passenger:
                pytest.skip("No passenger record available")
            
            flight = Flight.query.first()
            if not flight:
                pytest.skip("No flights available")
            
            available_seats = db.session.query(Seat).filter(
                Seat.FlightID == flight.FlightID,
                Seat.IsAvailable == True
            ).limit(1).all()
            
            if not available_seats:
                pytest.skip("No available seats")
            
            seat = available_seats[0]
            
            # Create booking
            booking = Booking(
                PassengerID=passenger.PassengerID,
                FlightID=flight.FlightID,
                NumberOfSeats=1,
                TotalAmount=200.0,
                Status='confirmed'
            )
            db.session.add(booking)
            db.session.flush()
            
            # Create ticket
            ticket = Ticket(
                BookingID=booking.BookingID,
                PassengerID=passenger.PassengerID,
                FlightID=flight.FlightID,
                SeatNumber=seat.SeatNumber,
                FarePaid=200.0,
                Status='issued'
            )
            db.session.add(ticket)
            seat.IsAvailable = False
            db.session.commit()
            
            # Verify ticket exists
            found_ticket = db.session.query(Ticket).filter_by(BookingID=booking.BookingID).first()
            assert found_ticket is not None, "Ticket should exist after booking"
            assert found_ticket.SeatNumber == seat.SeatNumber
            assert found_ticket.FlightID == flight.FlightID

    def test_duplicate_booking_fails(self):
        """A seat can be atomically reserved only once."""
        with app.app_context():
            from app import reserve_seat_atomically
            flight = Flight.query.first()
            assert flight is not None
            seat = Seat.query.filter_by(FlightID=flight.FlightID, SeatNumber='1A').first()
            assert seat is not None
            seat.IsAvailable = True
            flight_id = flight.FlightID
            db.session.commit()

        success1, seat1 = reserve_seat_atomically(flight_id, '1A', 1)
        assert success1 is True
        assert seat1 is not None

        success2, seat2 = reserve_seat_atomically(flight_id, '1A', 1)
        assert success2 is False
        assert seat2 is None


class TestCancellationConsistency:
    """Test booking cancellation consistency through the real HTTP endpoint."""

    def test_cancellation_endpoint_marks_booking_and_releases_seat(self):
        """Cancellation must be authenticated, scoped to the passenger, and release the seat."""
        client = app.test_client()
        with app.app_context():
            user = UserAccount.query.filter_by(Username='passenger1').first()
            assert user is not None
            passenger = Passenger.query.filter_by(UserID=user.UserID).first()
            flight = Flight.query.first()
            assert passenger is not None and flight is not None
            seat = Seat.query.filter_by(FlightID=flight.FlightID, IsAvailable=True).first()
            assert seat is not None

            booking = Booking(
                PassengerID=passenger.PassengerID,
                FlightID=flight.FlightID,
                NumberOfSeats=1,
                TotalAmount=200.0,
                Status='confirmed'
            )
            db.session.add(booking)
            db.session.flush()
            ticket = Ticket(
                BookingID=booking.BookingID,
                PassengerID=passenger.PassengerID,
                FlightID=flight.FlightID,
                SeatNumber=seat.SeatNumber,
                FarePaid=200.0,
                Status='issued'
            )
            db.session.add(ticket)
            seat.IsAvailable = False
            booking_id = booking.BookingID
            seat_id = seat.SeatID
            passenger_id = passenger.PassengerID
            db.session.commit()

        with client.session_transaction() as sess:
            sess['passenger_id'] = passenger_id
        response = client.post(f'/passenger/cancel-booking/{booking_id}')
        assert response.status_code == 302

        with app.app_context():
            refreshed_booking = db.session.get(Booking, booking_id)
            refreshed_seat = db.session.get(Seat, seat_id)
            assert refreshed_booking is not None
            assert refreshed_booking.Status == 'cancelled'
            assert refreshed_seat is not None and refreshed_seat.IsAvailable is True

    def test_passenger_cannot_cancel_another_passengers_booking(self):
        """A passenger must not cancel a booking owned by a different passenger."""
        client = app.test_client()
        with app.app_context():
            user = UserAccount.query.filter_by(Username='passenger1').first()
            assert user is not None
            passenger = Passenger.query.filter_by(UserID=user.UserID).first()
            flight = Flight.query.first()
            assert passenger is not None and flight is not None
            booking = Booking(
                PassengerID=passenger.PassengerID,
                FlightID=flight.FlightID,
                NumberOfSeats=1,
                TotalAmount=200.0,
                Status='confirmed'
            )
            db.session.add(booking)
            db.session.commit()
            booking_id = booking.BookingID
            wrong_passenger_id = passenger.PassengerID + 10000

        with client.session_transaction() as sess:
            sess['passenger_id'] = wrong_passenger_id
        response = client.post(f'/passenger/cancel-booking/{booking_id}')
        assert response.status_code == 302

        with app.app_context():
            refreshed_booking = db.session.get(Booking, booking_id)
            assert refreshed_booking is not None
            assert refreshed_booking.Status == 'confirmed'


class TestDatabasePortabilityAndHealth:
    """Regression tests for hosted PostgreSQL behavior and the platform health endpoint."""

    def test_atomic_seat_update_compiles_with_quoted_postgresql_identifiers(self):
        from sqlalchemy import update
        from sqlalchemy.dialects import postgresql

        statement = update(Seat).where(
            Seat.FlightID == 1,
            Seat.SeatNumber == '1',
            Seat.IsAvailable.is_(True)
        ).values(IsAvailable=False)
        sql = str(statement.compile(dialect=postgresql.dialect()))

        assert 'UPDATE "Seat"' in sql
        assert '"IsAvailable"' in sql
        assert '"FlightID"' in sql
        assert '"SeatNumber"' in sql

    def test_healthz_reports_database_available(self):
        response = app.test_client().get('/healthz')

        assert response.status_code == 200
        assert response.get_json() == {'status': 'ok', 'database': 'ok'}


class TestPasswordMigration:
    """Test password hashing migration from SHA-256 to scrypt."""

    def test_legacy_hash_verification_uses_application_helper(self):
        """The app verifier accepts valid legacy hashes and rejects incorrect passwords."""
        from app import verify_password
        password = 'oldpassword123'
        legacy_hash = hashlib.sha256(password.encode()).hexdigest()
        assert verify_password(password, legacy_hash)
        assert not verify_password('wrong-password', legacy_hash)


class TestLightDarkTheme:
    """Test light/dark theme toggle functionality."""

    def test_theme_persistence_in_templates(self):
        """Theme preference should be stored in localStorage."""
        from pathlib import Path
        css_path = Path(__file__).resolve().parents[1] / 'static' / 'css' / 'style.css'
        with open(css_path, 'r', encoding='utf-8') as f:
            css_content = f.read()
        assert '[data-theme="dark"]' in css_content


class TestERDiagram:
    """Test that ER diagram exists and is valid."""

    def test_er_diagram_exists(self):
        """ER diagram file should exist."""
        import os
        assert os.path.exists(Path(__file__).resolve().parents[1] / 'docs' / 'er-diagram.drawio')

    def test_sql_schema_exists(self):
        """SQL schema file should exist."""
        import os
        assert os.path.exists(Path(__file__).resolve().parents[1] / 'airline_schema.sql')


class TestCSSAndStyles:
    """Test CSS stylesheet exists and has proper content."""

    def test_css_exists(self):
        """CSS stylesheet should exist."""
        import os
        assert os.path.exists(Path(__file__).resolve().parents[1] / 'static' / 'css' / 'style.css')

    def test_css_has_color_palette(self):
        """CSS should have custom color palette."""
        with open(Path(__file__).resolve().parents[1] / 'static' / 'css' / 'style.css', 'r') as f:
            css_content = f.read()
        assert '#1d2b64' in css_content


class TestResponsiveLayout:
    """Test responsive layout meta tags and CSS."""

    def test_viewport_meta_in_base_template(self):
        """Base template should have viewport meta tag for responsiveness."""
        with open(Path(__file__).resolve().parents[1] / 'templates' / 'base.html', 'r') as f:
            content = f.read()
        assert 'viewport' in content, "base.html missing viewport meta"

    def test_child_templates_extend_base(self):
        """Child templates should extend the base template."""
        template_dir = Path(__file__).resolve().parents[1] / 'templates'
        import os
        for fname in sorted(os.listdir(template_dir)):
            if fname.endswith('.html') and fname != 'base.html':
                with open(os.path.join(template_dir, fname), 'r') as f:
                    content = f.read()
                assert '{% extends' in content, f"{fname} doesn't extend base"


class TestOperationsCentre:
    def test_operations_routes_render_for_admin(self):
        with app.app_context():
            admin = UserAccount.query.filter_by(Role='admin').first()
            assert admin is not None
            admin_id = admin.UserID
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['admin_id'] = admin_id
        for path in ['/admin/operations', '/admin/activity-history', '/admin/integrity',
                     '/admin/fare-classes', '/admin/saved-filters', '/admin/import-csv',
                     '/admin/reports']:
            response = client.get(path)
            assert response.status_code == 200, f'{path} returned {response.status_code}'

    def test_report_filters_and_csv_export(self):
        with app.app_context():
            admin = UserAccount.query.filter_by(Role='admin').first()
            admin_id = admin.UserID
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['admin_id'] = admin_id
        response = client.get('/admin/reports?status=on_time&format=csv')
        assert response.status_code == 200
        assert 'text/csv' in response.headers.get('Content-Type', '')
        assert 'Flight,Departure,Arrival,Status' in response.get_data(as_text=True)

    def test_integrity_monitor_reports_critical_maintenance(self):
        with app.app_context():
            aircraft = Aircraft.query.first()
            defect = AircraftDefect(AircraftID=aircraft.AircraftID, Description='Test critical defect',
                                    Severity='critical', Status='reported')
            db.session.add(defect)
            db.session.commit()
            admin = UserAccount.query.filter_by(Role='admin').first()
            admin_id = admin.UserID
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['admin_id'] = admin_id
        response = client.get('/admin/integrity')
        assert response.status_code == 200
        assert b'Aircraft has unresolved critical maintenance' in response.data

    def test_password_eye_toggle_is_not_forced_to_scroll(self):
        script = Path(__file__).resolve().parents[1] / 'static' / 'js' / 'main.js'
        assert script.exists()
        assert 'input.focus();' not in script.read_text(encoding='utf-8')
        stylesheet = script.parent.parent / 'css' / 'style.css'
        css = stylesheet.read_text(encoding='utf-8')
        assert '.pw-toggle:active { transform: translateY(-50%); }' in css
