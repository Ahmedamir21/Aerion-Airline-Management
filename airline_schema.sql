-- Airline Management System Database Schema
-- Generated from SQLite database
-- Note: Adapt for SQL Server as needed
--

-- CREATE TABLE statements
CREATE TABLE "Aircraft" (
	"AircraftID" INTEGER NOT NULL, 
	"RegistrationNumber" VARCHAR(20) NOT NULL, 
	"Model" VARCHAR(50) NOT NULL, 
	"TotalSeats" INTEGER NOT NULL, 
	"SeatConfiguration" VARCHAR(50), 
	PRIMARY KEY ("AircraftID"), 
	UNIQUE ("RegistrationNumber")
);

CREATE TABLE "Airport" (
	"AirportID" INTEGER NOT NULL, 
	"Code" VARCHAR(10) NOT NULL, 
	"Name" VARCHAR(100) NOT NULL, 
	"City" VARCHAR(50) NOT NULL, 
	"Country" VARCHAR(50), 
	PRIMARY KEY ("AirportID"), 
	UNIQUE ("Code")
);

CREATE TABLE "Baggage" (
	"BaggageID" INTEGER NOT NULL, 
	"TicketID" INTEGER NOT NULL, 
	"TagNumber" VARCHAR(20) NOT NULL, 
	"Weight" FLOAT, 
	"Status" VARCHAR(20) NOT NULL, 
	"CheckedDate" DATETIME NOT NULL, 
	PRIMARY KEY ("BaggageID"), 
	FOREIGN KEY("TicketID") REFERENCES "Ticket" ("TicketID")
);

CREATE TABLE "Booking" (
	"BookingID" INTEGER NOT NULL, 
	"PassengerID" INTEGER NOT NULL, 
	"FlightID" INTEGER NOT NULL, 
	"NumberOfSeats" INTEGER NOT NULL, 
	"TotalAmount" FLOAT NOT NULL, 
	"BookingDate" DATETIME NOT NULL, 
	"Status" VARCHAR(20) NOT NULL, 
	PRIMARY KEY ("BookingID"), 
	FOREIGN KEY("PassengerID") REFERENCES "Passenger" ("PassengerID"), 
	FOREIGN KEY("FlightID") REFERENCES "Flight" ("FlightID")
);

CREATE TABLE "CrewMember" (
	"CrewID" INTEGER NOT NULL, 
	"UserID" INTEGER NOT NULL, 
	"Name" VARCHAR(100) NOT NULL, 
	"Role" VARCHAR(50) NOT NULL, 
	"LicenseNumber" VARCHAR(30), 
	"Base" VARCHAR(50), 
	PRIMARY KEY ("CrewID"), 
	UNIQUE ("UserID"), 
	FOREIGN KEY("UserID") REFERENCES "UserAccount" ("UserID")
);

CREATE TABLE "Employee" (
	"EmployeeID" INTEGER NOT NULL, 
	"UserID" INTEGER NOT NULL, 
	"Name" VARCHAR(100) NOT NULL, 
	"Position" VARCHAR(50) NOT NULL, 
	"PhoneExtension" VARCHAR(10), 
	PRIMARY KEY ("EmployeeID"), 
	UNIQUE ("UserID"), 
	FOREIGN KEY("UserID") REFERENCES "UserAccount" ("UserID")
);

CREATE TABLE "Flight" (
	"FlightID" INTEGER NOT NULL, 
	"RouteID" INTEGER NOT NULL, 
	"AircraftID" INTEGER NOT NULL, 
	"FlightNumber" VARCHAR(10) NOT NULL, 
	"DepartureTime" DATETIME NOT NULL, 
	"ArrivalTime" DATETIME NOT NULL, 
	"Status" VARCHAR(20) NOT NULL, 
	"FareClass" VARCHAR(30), 
	PRIMARY KEY ("FlightID"), 
	FOREIGN KEY("RouteID") REFERENCES "Route" ("RouteID"), 
	FOREIGN KEY("AircraftID") REFERENCES "Aircraft" ("AircraftID")
);

CREATE TABLE "LoyaltyAccount" (
	"LoyaltyID" INTEGER NOT NULL, 
	"PassengerID" INTEGER NOT NULL, 
	"MilesBalance" INTEGER NOT NULL, 
	"MilesEarnedTotal" INTEGER NOT NULL, 
	"LastEarnedDate" DATETIME, 
	"LastRedeemedDate" DATETIME, 
	PRIMARY KEY ("LoyaltyID"), 
	UNIQUE ("PassengerID"), 
	FOREIGN KEY("PassengerID") REFERENCES "Passenger" ("PassengerID")
);

CREATE TABLE "Passenger" (
	"PassengerID" INTEGER NOT NULL, 
	"UserID" INTEGER NOT NULL, 
	"Name" VARCHAR(100) NOT NULL, 
	"PassportNumber" VARCHAR(20) NOT NULL, 
	"ContactInfo" VARCHAR(200), 
	PRIMARY KEY ("PassengerID"), 
	UNIQUE ("UserID"), 
	FOREIGN KEY("UserID") REFERENCES "UserAccount" ("UserID")
);

CREATE TABLE "Payment" (
	"PaymentID" INTEGER NOT NULL, 
	"BookingID" INTEGER NOT NULL, 
	"Amount" FLOAT NOT NULL, 
	"PaymentMethod" VARCHAR(50), 
	"PaymentDate" DATETIME NOT NULL, 
	"TransactionID" VARCHAR(50), 
	PRIMARY KEY ("PaymentID"), 
	FOREIGN KEY("BookingID") REFERENCES "Booking" ("BookingID"), 
	UNIQUE ("TransactionID")
);

CREATE TABLE "Route" (
	"RouteID" INTEGER NOT NULL, 
	"DepartureAirportID" INTEGER NOT NULL, 
	"ArrivalAirportID" INTEGER NOT NULL, 
	"Distance" INTEGER, 
	"BaseFare" FLOAT NOT NULL, 
	PRIMARY KEY ("RouteID"), 
	FOREIGN KEY("DepartureAirportID") REFERENCES "Airport" ("AirportID"), 
	FOREIGN KEY("ArrivalAirportID") REFERENCES "Airport" ("AirportID")
);

CREATE TABLE "Seat" (
	"SeatID" INTEGER NOT NULL, 
	"FlightID" INTEGER NOT NULL, 
	"SeatNumber" VARCHAR(10) NOT NULL, 
	"Class" VARCHAR(20) NOT NULL, 
	"IsAvailable" BOOLEAN, 
	PRIMARY KEY ("SeatID"), 
	UNIQUE ("FlightID", "SeatNumber"), 
	FOREIGN KEY("FlightID") REFERENCES "Flight" ("FlightID")
);

CREATE TABLE "Ticket" (
	"TicketID" INTEGER NOT NULL, 
	"BookingID" INTEGER NOT NULL, 
	"PassengerID" INTEGER NOT NULL, 
	"FlightID" INTEGER NOT NULL, 
	"SeatNumber" VARCHAR(10) NOT NULL, 
	"FarePaid" FLOAT NOT NULL, 
	"IssueDate" DATETIME NOT NULL, 
	"Status" VARCHAR(20) NOT NULL, 
	PRIMARY KEY ("TicketID"), 
	UNIQUE ("BookingID"), 
	FOREIGN KEY("BookingID") REFERENCES "Booking" ("BookingID"), 
	FOREIGN KEY("PassengerID") REFERENCES "Passenger" ("PassengerID"), 
	FOREIGN KEY("FlightID") REFERENCES "Flight" ("FlightID")
);

CREATE TABLE "UserAccount" (
	"UserID" INTEGER NOT NULL, 
	"Username" VARCHAR(50) NOT NULL, 
	"Password" VARCHAR(255) NOT NULL, 
	"Role" VARCHAR(20) NOT NULL, 
	PRIMARY KEY ("UserID"), 
	UNIQUE ("Username")
);

CREATE TABLE "EmployeeQualification" (
    "QualificationID" INTEGER PRIMARY KEY,
    "EmployeeID" INTEGER NOT NULL,
    "QualificationName" VARCHAR(50) NOT NULL,
    "AuthorizedAircraftType" VARCHAR(50),
    "IssuedDate" DATETIME,
    "ExpiryDate" DATETIME,
    FOREIGN KEY ("EmployeeID") REFERENCES "Employee" ("EmployeeID")
);

CREATE TABLE "EmployeeShift" (
    "ShiftID" INTEGER PRIMARY KEY,
    "EmployeeID" INTEGER NOT NULL,
    "Date" DATE NOT NULL,
    "ShiftType" VARCHAR(20) NOT NULL,
    "Status" VARCHAR(20) NOT NULL DEFAULT 'assigned',
    "AssignedTask" VARCHAR(100),
    FOREIGN KEY ("EmployeeID") REFERENCES "Employee" ("EmployeeID")
);

CREATE TABLE "MaintenanceWorkOrder" (
    "WorkOrderID" INTEGER PRIMARY KEY,
    "AircraftID" INTEGER NOT NULL,
    "Description" VARCHAR(200) NOT NULL,
    "Severity" VARCHAR(20) NOT NULL,
    "Status" VARCHAR(20) NOT NULL DEFAULT 'pending',
    "ReportedDate" DATETIME NOT NULL,
    "ResolvedDate" DATETIME,
    "AssignedTechnicianID" INTEGER,
    "ApprovedByID" INTEGER,
    "ApprovalDate" DATETIME,
    FOREIGN KEY ("AircraftID") REFERENCES "Aircraft" ("AircraftID"),
    FOREIGN KEY ("AssignedTechnicianID") REFERENCES "Employee" ("EmployeeID"),
    FOREIGN KEY ("ApprovedByID") REFERENCES "Employee" ("EmployeeID")
);

CREATE TABLE "AircraftDefect" (
    "DefectID" INTEGER PRIMARY KEY,
    "AircraftID" INTEGER NOT NULL,
    "Description" VARCHAR(200) NOT NULL,
    "Severity" VARCHAR(20) NOT NULL,
    "Status" VARCHAR(20) NOT NULL DEFAULT 'reported',
    "ReportedDate" DATETIME NOT NULL,
    "ResolvedDate" DATETIME,
    "RelatedWorkOrderID" INTEGER,
    FOREIGN KEY ("AircraftID") REFERENCES "Aircraft" ("AircraftID"),
    FOREIGN KEY ("RelatedWorkOrderID") REFERENCES "MaintenanceWorkOrder" ("WorkOrderID")
);


-- Simulated refunds; no external payment gateway is connected.
CREATE TABLE "Refund" (
    "RefundID" INTEGER NOT NULL PRIMARY KEY,
    "BookingID" INTEGER NOT NULL,
    "PaymentID" INTEGER NOT NULL UNIQUE,
    "Amount" FLOAT NOT NULL,
    "RefundDate" DATETIME NOT NULL,
    "Reason" VARCHAR(200) NOT NULL,
    "TransactionID" VARCHAR(60) NOT NULL UNIQUE,
    "Status" VARCHAR(20) NOT NULL DEFAULT 'simulated',
    FOREIGN KEY ("BookingID") REFERENCES "Booking" ("BookingID"),
    FOREIGN KEY ("PaymentID") REFERENCES "Payment" ("PaymentID")
);


-- Operations-centre additions (created additively; existing coursework tables remain unchanged).
CREATE TABLE "AuditLog" (
    "AuditID" INTEGER PRIMARY KEY,
    "ActorUserID" INTEGER,
    "ActorUsername" VARCHAR(50) NOT NULL DEFAULT 'system',
    "Action" VARCHAR(100) NOT NULL,
    "EntityType" VARCHAR(80) NOT NULL,
    "EntityID" VARCHAR(80),
    "Details" TEXT,
    "CreatedAt" DATETIME NOT NULL,
    FOREIGN KEY ("ActorUserID") REFERENCES "UserAccount" ("UserID")
);
CREATE INDEX "ix_AuditLog_CreatedAt" ON "AuditLog" ("CreatedAt");

CREATE TABLE "SavedFilter" (
    "FilterID" INTEGER PRIMARY KEY,
    "UserID" INTEGER NOT NULL,
    "Name" VARCHAR(80) NOT NULL,
    "QueryString" VARCHAR(1000) NOT NULL DEFAULT '',
    "CreatedAt" DATETIME NOT NULL,
    UNIQUE ("UserID", "Name"),
    FOREIGN KEY ("UserID") REFERENCES "UserAccount" ("UserID")
);
CREATE INDEX "ix_SavedFilter_UserID" ON "SavedFilter" ("UserID");

CREATE TABLE "FareClass" (
    "FareClassID" INTEGER PRIMARY KEY,
    "Code" VARCHAR(30) NOT NULL UNIQUE,
    "Name" VARCHAR(60) NOT NULL,
    "Multiplier" FLOAT NOT NULL DEFAULT 1.0,
    "Active" BOOLEAN NOT NULL DEFAULT 1
);

CREATE TABLE "RouteWaypoint" (
    "WaypointID" INTEGER PRIMARY KEY,
    "RouteID" INTEGER NOT NULL,
    "Sequence" INTEGER NOT NULL,
    "Label" VARCHAR(100) NOT NULL,
    "Latitude" FLOAT NOT NULL,
    "Longitude" FLOAT NOT NULL,
    "PlannedAltitudeFt" INTEGER NOT NULL DEFAULT 30000,
    "PlannedSpeedKts" INTEGER NOT NULL DEFAULT 450,
    "StopAirportID" INTEGER,
    UNIQUE ("RouteID", "Sequence"),
    FOREIGN KEY ("RouteID") REFERENCES "Route" ("RouteID"),
    FOREIGN KEY ("StopAirportID") REFERENCES "Airport" ("AirportID")
);
CREATE INDEX "ix_RouteWaypoint_RouteID" ON "RouteWaypoint" ("RouteID");

CREATE TABLE "ImportBatch" (
    "BatchID" INTEGER PRIMARY KEY,
    "UploadedByUserID" INTEGER,
    "FileName" VARCHAR(255) NOT NULL,
    "TotalRows" INTEGER NOT NULL DEFAULT 0,
    "ImportedRows" INTEGER NOT NULL DEFAULT 0,
    "RejectedRows" INTEGER NOT NULL DEFAULT 0,
    "Status" VARCHAR(20) NOT NULL DEFAULT 'validated',
    "CreatedAt" DATETIME NOT NULL,
    FOREIGN KEY ("UploadedByUserID") REFERENCES "UserAccount" ("UserID")
);
