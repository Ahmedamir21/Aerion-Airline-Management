"""Employees can also fly as passengers, with a staff discount."""
from datetime import datetime

from app import (
    app, db, UserAccount, Employee, Passenger, LoyaltyAccount, Flight, Seat, Booking,
    STAFF_DISCOUNT_PERCENT,
)
from tests.test_airline import setup_and_teardown  # noqa: F401  (autouse fixture)


def _future_flight():
    return Flight.query.filter(Flight.DepartureTime > datetime.utcnow(), Flight.Status == 'scheduled').first() \
        or Flight.query.filter(Flight.DepartureTime > datetime.utcnow()).first()


def _staff_client():
    client = app.test_client()
    with app.app_context():
        user = UserAccount.query.filter_by(Role='staff').first()
        employee = Employee.query.filter_by(UserID=user.UserID).first()
        employee_id, user_id = employee.EmployeeID, user.UserID
    with client.session_transaction() as sess:
        sess['staff_id'] = employee_id
    return client, user_id


def test_staff_without_profile_is_sent_to_profile_page_when_booking_is_for_self():
    client, _ = _staff_client()
    page = client.get('/passenger/profile')
    assert page.status_code == 200 and b'Passport number' in page.data


def test_staff_creates_profile_with_loyalty_account_and_keeps_one_account():
    client, user_id = _staff_client()
    response = client.post('/passenger/profile', data={'passport': 'EG1234567', 'contact': 'a@b.c'})
    assert response.status_code == 302
    with app.app_context():
        profile = Passenger.query.filter_by(UserID=user_id).one()
        assert LoyaltyAccount.query.filter_by(PassengerID=profile.PassengerID).count() == 1
        assert UserAccount.query.get(user_id).Role == 'staff'


def test_profile_rejects_bad_passport():
    client, user_id = _staff_client()
    response = client.post('/passenger/profile', data={'passport': '!!'})
    assert response.status_code == 400
    with app.app_context():
        assert Passenger.query.filter_by(UserID=user_id).count() == 0


def test_passenger_account_cannot_open_employee_profile_page():
    client = app.test_client()
    with app.app_context():
        passenger = Passenger.query.first()
        passenger_id = passenger.PassengerID
    with client.session_transaction() as sess:
        sess['passenger_id'] = passenger_id
    response = client.get('/passenger/profile')
    assert response.status_code == 302 and '/login' in response.headers['Location']


def test_staff_booking_for_self_gets_staff_discount_and_earns_miles():
    client, user_id = _staff_client()
    client.post('/passenger/profile', data={'passport': 'EG1234567'})
    with app.app_context():
        profile = Passenger.query.filter_by(UserID=user_id).one()
        flight = _future_flight()
        seat = Seat.query.filter_by(FlightID=flight.FlightID, IsAvailable=True, Class='economy').first()
        flight_id, seat_number, profile_id = flight.FlightID, seat.SeatNumber, profile.PassengerID
        from app import seat_prices
        list_price = seat_prices(flight.Route)['economy']
    with client.session_transaction() as sess:
        sess['passenger_id'] = profile_id
    response = client.post(f'/passenger/book/{flight_id}', data={'seats': seat_number, 'booking_for': 'self'})
    assert response.status_code == 302
    with app.app_context():
        booking = Booking.query.filter_by(PassengerID=profile_id).one()
        assert round(booking.TotalAmount, 2) == round(list_price * (1 - STAFF_DISCOUNT_PERCENT / 100), 2)
        assert LoyaltyAccount.query.filter_by(PassengerID=profile_id).one().MilesBalance > 0


def test_staff_counter_booking_for_a_passenger_has_no_staff_discount():
    client, user_id = _staff_client()
    client.post('/passenger/profile', data={'passport': 'EG1234567'})
    with app.app_context():
        owner = UserAccount.query.filter_by(Username='passenger1').one()
        target = Passenger.query.filter_by(UserID=owner.UserID).one()
        flight = _future_flight()
        seat = Seat.query.filter_by(FlightID=flight.FlightID, IsAvailable=True, Class='economy').first()
        flight_id, seat_number, target_id = flight.FlightID, seat.SeatNumber, target.PassengerID
        own_id = Passenger.query.filter_by(UserID=user_id).one().PassengerID
        from app import seat_prices
        list_price = seat_prices(flight.Route)['economy']
    with client.session_transaction() as sess:
        sess['passenger_id'] = own_id
    response = client.post(f'/passenger/book/{flight_id}', data={
        'seats': seat_number, 'booking_for': 'other', 'passenger_username': 'passenger1'})
    assert response.status_code == 302
    with app.app_context():
        booking = Booking.query.filter_by(PassengerID=target_id).order_by(Booking.BookingID.desc()).first()
        assert round(booking.TotalAmount, 2) == round(list_price, 2)


def test_new_passenger_signup_gets_a_loyalty_account():
    client = app.test_client()
    client.post('/register', data={'name': 'New Person', 'username': 'newperson', 'password': 'password123',
                                   'confirm_password': 'password123', 'passport': 'AB12345'})
    with app.app_context():
        user = UserAccount.query.filter_by(Username='newperson').one()
        passenger = Passenger.query.filter_by(UserID=user.UserID).one()
        assert LoyaltyAccount.query.filter_by(PassengerID=passenger.PassengerID).count() == 1


def test_booking_page_shows_counter_only_for_staff_without_profile_and_choice_with_profile():
    client, user_id = _staff_client()
    with app.app_context():
        flight_id = _future_flight().FlightID
    page = client.get(f'/passenger/book/{flight_id}')
    assert b'Passenger username' in page.data and b'id="booking-for"' not in page.data
    client.post('/passenger/profile', data={'passport': 'EG1234567'})
    page = client.get(f'/passenger/book/{flight_id}')
    assert b'id="booking-for"' in page.data and b'Staff discount: 10% off' in page.data
