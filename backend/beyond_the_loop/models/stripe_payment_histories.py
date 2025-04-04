from datetime import datetime
from decimal import Decimal
from typing import Optional, List

# SQLAlchemy imports
from sqlalchemy import (
    String, Text, Boolean, Column, DECIMAL, ForeignKey, DateTime, JSON, func
)
from sqlalchemy.orm import relationship

# Internal imports
from open_webui.internal.db import Base, get_db


class StripePaymentHistory(Base):
    __tablename__ = "stripe_payment_history"

    id = Column(String, primary_key=True, unique=True)
    stripe_transaction_id = Column(String, unique=True, nullable=False)
    company_id = Column(String, ForeignKey("company.id"), nullable=False)
    user_id = Column(String, ForeignKey("user.id"), nullable=True)

    description = Column(Text, nullable=False, default="Standard Subscription Charge")
    charged_amount = Column(DECIMAL(10, 2), nullable=False)
    currency = Column(String, nullable=False, default="EUR")
    payment_status = Column(String, nullable=False)  # Example: "succeeded", "failed"
    payment_method = Column(String, nullable=True)  # Example: "card", "bank_transfer"
    payment_date = Column(DateTime, nullable=False, default=datetime.utcnow)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    payment_metadata = Column(JSON, nullable=True)

    company = relationship("Company")
    user = relationship('User', foreign_keys=[user_id])


class StripePaymentHistoryTable:
    """Service class for managing StripePaymentHistory records."""

    def log_payment(self, payment_data: dict) -> Optional[StripePaymentHistory]:
        """
        Logs a new payment record in the database.
        
        This method creates a new StripePaymentHistory using the provided payment data.
        It opens a database session, adds the new record, commits the transaction, and
        refreshes the record to capture any database-generated values. If an error occurs
        during this process, the error is printed and None is returned.
        """
        try:
            with get_db() as db:
                new_payment = StripePaymentHistory(**payment_data)
                db.add(new_payment)
                db.commit()
                db.refresh(new_payment)
                return new_payment
        except Exception as e:
            print(f"Error logging payment: {e}")
            return None

    def get_payment_by_id(self, payment_id: str) -> Optional[StripePaymentHistory]:
        """
        Retrieve a payment record using its unique ID.
        
        This method queries the database for a StripePaymentHistory record that matches the
        provided payment_id. If an error occurs or no record is found, it returns None.
        
        Args:
            payment_id: Unique identifier of the payment record.
        
        Returns:
            The corresponding StripePaymentHistory instance if found, or None otherwise.
        """
        try:
            with get_db() as db:
                payment = db.query(StripePaymentHistory).filter_by(id=payment_id).first()
                return payment
        except Exception as e:
            print(f"Error fetching payment by ID: {e}")
            return None

    def get_payments_for_company(self, company_id: str) -> List[StripePaymentHistory]:
        """
        Retrieve payments for a specific company.
        
        Queries the database for all payment records associated with the given company 
        identifier. If an exception occurs during the database query, an error message is 
        printed and an empty list is returned.
        
        Args:
            company_id: The unique identifier for the company.
        
        Returns:
            A list of StripePaymentHistory instances if the query is successful, or an 
            empty list in case of an error.
        """
        try:
            with get_db() as db:
                payments = db.query(StripePaymentHistory).filter_by(company_id=company_id).all()
                return payments
        except Exception as e:
            print(f"Error fetching payments for company {company_id}: {e}")
            return []

    def get_payments_for_user(self, user_id: str) -> List[StripePaymentHistory]:
        """Retrieve all payment records for a specified user.
        
        Fetches and returns all StripePaymentHistory records that correspond to the given user ID.
        If an error occurs during the database query, an error message is printed and an empty list is returned.
        """
        try:
            with get_db() as db:
                payments = db.query(StripePaymentHistory).filter_by(user_id=user_id).all()
                return payments
        except Exception as e:
            print(f"Error fetching payments for user {user_id}: {e}")
            return []


StripePaymentHistories = StripePaymentHistoryTable()
