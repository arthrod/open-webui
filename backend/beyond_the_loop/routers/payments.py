import stripe
from datetime import datetime
from pydantic import BaseModel
from fastapi import Depends, HTTPException, Request, Header, APIRouter
import os
import json

from beyond_the_loop.models.users import Users
from beyond_the_loop.models.companies import Companies
from beyond_the_loop.models.stripe_payment_histories import StripePaymentHistories

from open_webui.utils.auth import get_verified_user

router = APIRouter()

webhook_secret = os.environ.get('WEBHOOK_SECRET')
stripe.api_key = os.environ.get('STRIPE_API_KEY')

# Constants
AMOUNT = 2500 # Amount in cents (e.g., 25 euro)
CREDITS_TO_ADD = 20000

def create_and_finalize_invoice(stripe_customer_id, payment_intent_id, description="Credits Purchase"):
    """
    Creates and finalizes an invoice for a Stripe customer.
    
    This function creates an invoice item linked to a payment intent and then
    generates an invoice that is automatically finalized. The invoice item uses
    a fixed amount defined by the AMOUNT constant and the EUR currency. An HTTPException
    with a 500 status code is raised if the invoice creation or finalization fails.
    
    Args:
        stripe_customer_id: The identifier of the Stripe customer.
        payment_intent_id: The payment intent identifier to record in the invoice metadata.
        description: An optional description for the invoice item (default is "Credits Purchase").
    
    Returns:
        The finalized invoice object from the Stripe API.
    
    Raises:
        HTTPException: If an error occurs while creating the invoice item or invoice.
    """
    try:
        # Create an invoice item
        stripe.InvoiceItem.create(
            customer=stripe_customer_id,
            description=description,
            amount=AMOUNT,
            currency="eur",
            metadata={"payment_intent_id": payment_intent_id},
        )

        # Create the invoice
        invoice = stripe.Invoice.create(
            customer=stripe_customer_id,
            auto_advance=True  # Automatically finalize the invoice
        )

        return invoice

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create-checkout-session/")
async def create_checkout_session(user=Depends(get_verified_user)):
    """Create a Stripe Checkout session for a verified user to purchase credits.
    
    Initializes a Stripe Checkout session with payment details for purchasing credits.
    If the user already has a Stripe customer ID, it is used; otherwise, a new customer is
    created using the user's email. Returns a dictionary containing the URL for the session.
    
    Returns:
        dict: A dictionary with a "url" key for the Stripe Checkout session.
    
    Raises:
        HTTPException: If an error occurs during session creation.
    """
    try:
        # Create a Stripe Checkout session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {
                        'name': 'Credits',
                    },
                    'unit_amount': AMOUNT,
                },
                'quantity': 1,
            }],
            mode='payment',
            customer=user.stripe_customer_id if user.stripe_customer_id else None,
            customer_email=None if user.stripe_customer_id else user.email,
            customer_creation='always' if not user.stripe_customer_id else None,  # Always create a customer if they don't have one
            success_url=f'https://www.google.com',  # Frontend success page
            cancel_url=f'https://www.google.com',  # Frontend cancel page
            payment_intent_data={
                'metadata': {
                    'from_checkout_session': 'true'
                },
                'setup_future_usage': 'off_session'  # This tells Stripe to save the payment method
            }
        )
        return {"url": session.url}
    except Exception as e:
        print("ERROR:::: ", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/checkout-webhook")
async def checkout_webhook(request: Request, stripe_signature: str = Header(None)):
    """
    Process incoming Stripe webhook events.
    
    This asynchronous function verifies the Stripe webhook signature from the request and
    dispatches the event to the appropriate handler based on its type. For recognized event
    types—such as completed checkout sessions, successful payment intents, payment method
    attachments or detachments, and payment failures—it calls the corresponding handler.
    Unhandled event types are logged and a success message is returned.
    
    Raises:
        HTTPException: If the Stripe signature is missing or invalid (HTTP 400), or if an error
            occurs during event processing (HTTP 500).
    """
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="No Stripe signature provided")

    payload = await request.body()
    try:
        # Verify Stripe Webhook Signature
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=stripe_signature,
            secret=webhook_secret
        )

        event_type = event.get("type")
        event_data = event.get("data", {}).get("object", {})

        # Handle Stripe events
        if event_type == "checkout.session.completed":
            if event_data.get("payment_status") == "paid":
                handle_checkout_session_completed(event_data)
                return

        elif event_type == "payment_intent.succeeded":
            handle_payment_intent_succeeded(event_data)
            return

        elif event_type == 'payment_method.attached':
            handle_payment_method_attached(event_data)
            return

        elif event_type == 'payment_method.detached':
            handle_payment_method_detached(event_data)
            return

        elif event_type == "payment_intent.payment_failed":
            handle_payment_failed(event_data)
            return

        else:
            print(f"Unhandled Stripe event type: {event_type}")

        return {"message": "Webhook processed successfully"}

    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except Exception as e:
        print(f"Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def handle_payment_failed(event_data):
    """
    Logs a failed payment event.
    
    Extracts payment intent and error details from the provided event data, retrieves the associated user
    and company based on the customer's email, and logs the failed payment. If the customer's email cannot
    be determined, an error message is printed instead.
    
    Parameters:
        event_data (dict): A dictionary containing details of the failed payment event from Stripe, including
                           payment intent ID, charges, metadata, and failure error information.
    """
    try:
        payment_intent_id = event_data.get("id")
        charges = event_data.get("charges", {}).get("data", [])
        customer_email = charges[0].get("billing_details", {}).get("email") if charges else None
        failure_reason = event_data.get("last_payment_error", {}).get("message", "Unknown reason")

        if not customer_email:
            customer_email = event_data.get("metadata", {}).get("customer_email")

        if not customer_email:
            print(f"Failed payment: Customer email not found for PaymentIntent {payment_intent_id}.")
            return

        user = Users.get_user_by_email(customer_email)
        company = Companies.get_company_by_id(user.company_id) if user else None

        payment_data = {
            "id": f"payment_{payment_intent_id}",
            "stripe_transaction_id": payment_intent_id,
            "company_id": company.id if company else None,
            "user_id": user.id if user else None,
            "description": "Payment Failed",
            "charged_amount": event_data.get("amount", 0),
            "currency": event_data.get("currency", "unknown"),
            "payment_status": "failed",
            "payment_method": "card",
            "payment_date": datetime.utcfromtimestamp(event_data.get("created", datetime.utcnow().timestamp())),
            "payment_metadata": event_data.get("metadata", {}),
            "failure_reason": failure_reason,
        }

        StripePaymentHistories.log_payment(payment_data)

        print(f"Logged failed payment for {customer_email} with reason: {failure_reason}")

    except Exception as e:
        print(f"Error handling payment_intent.payment_failed: {e}")


def handle_checkout_session_completed(data):
    """
    Processes a successful Stripe checkout session event.
    
    This function updates user and company records following a completed Stripe checkout session.
    It saves the Stripe Customer ID for the user if not already set, adds credits to the company's
    balance, updates the company's stored card details (enabling auto-recharge), sets the default
    payment method for future transactions, creates and finalizes an invoice, and logs the payment
    history.
    
    Args:
        data (dict): Event data from Stripe containing checkout session details such as customer
            information, payment intent identifier, amount charged, and transaction metadata.
    
    Raises:
        Exception: If required fields are missing in the event data.
    """
    user_email = data["customer_details"]["email"]
    user = Users.get_user_by_email(user_email)

    try:
        # Save Stripe Customer ID if missing
        if user.stripe_customer_id is None:
            Users.update_user_by_id(user.id, {"stripe_customer_id": data["customer"]})

        # Update company credits
        company = Companies.get_company_by_id(user.company_id)

        Companies.add_credit_balance(user.company_id, CREDITS_TO_ADD)

        # Get payment method details and update card number
        payment_intent = stripe.PaymentIntent.retrieve(data["payment_intent"])
        if payment_intent.payment_method:
            payment_method = stripe.PaymentMethod.retrieve(payment_intent.payment_method)
            if payment_method.card:
                new_card_number = f"**** **** **** {payment_method.card.last4}"
                Companies.update_company_by_id(user.company_id, {
                    "credit_card_number": new_card_number,
                    "auto_recharge": True  # Enable auto-recharge by default when card is saved
                })

                # Set this payment method as the default for future payments
                stripe.Customer.modify(
                    data["customer"],
                    invoice_settings={
                        'default_payment_method': payment_intent.payment_method
                    }
                )

        create_and_finalize_invoice(
            stripe_customer_id=data["customer"],
            payment_intent_id=data["payment_intent"],
            description="Credits Purchase via Checkout"
        )

        # Log payment history
        payment_date = datetime.utcfromtimestamp(data["created"])
        payment_data = {
            "id": f"payment_{data['id']}",
            "stripe_transaction_id": data["id"],
            "company_id": company.id,
            "user_id": user.id,
            "description": "Credits Purchase",
            "charged_amount": data["amount_total"],
            "currency": data["currency"],
            "payment_status": data["payment_status"],
            "payment_method": "card",
            "payment_date": payment_date,
            "payment_metadata": data.get("metadata", {}),
        }

        StripePaymentHistories.log_payment(payment_data)

    except KeyError as e:
        raise Exception("Invalid data structure in checkout.session.completed event")
    except Exception as e:
        raise


def handle_payment_intent_succeeded(data):
    """
    Processes a Stripe payment_intent.succeeded event by updating company credits and
    creating an invoice for off-session payments.
    
    If the event payload's metadata indicates it originates from a checkout session,
    no action is taken. Otherwise, the function retrieves the user by the Stripe customer
    ID, updates the associated company's credit balance using a provided or default credit
    amount, and finalizes an invoice using the payment intent details.
    
    Args:
        data (dict): Stripe event payload expected to include "customer", "id", and "metadata".
            The metadata may contain "from_checkout_session" (to skip processing) and
            "credits_to_add" (the credits to add, as a string or integer).
    
    Raises:
        Exception: If the required data structure is missing keys or no user is found for
            the provided Stripe customer ID.
    """
    try:
        # Skip if this is from a checkout session - credits are handled there
        if data.get("metadata", {}).get("from_checkout_session"):
            return

        user = Users.get_user_by_stripe_customer_id(data["customer"])

        if not user:
            raise Exception(f"No user found with stripe customer id: {data['customer']}")

        # Update company credits
        credits_to_add = data.get("metadata", {}).get("credits_to_add", CREDITS_TO_ADD)  # Use metadata if available
        if isinstance(credits_to_add, str):
            credits_to_add = int(credits_to_add)  # Convert string to integer if needed

        Companies.add_credit_balance(user.company_id, credits_to_add)

        create_and_finalize_invoice(
            stripe_customer_id=user.stripe_customer_id,
            payment_intent_id=data["id"],
            description="Credits Purchase via Off-Session Payment"
        )

    except KeyError as e:
        raise Exception("Invalid data structure in payment_intent.succeeded event")
    except Exception as e:
        raise


@router.post("/charge-customer/")
async def charge_customer(user=Depends(get_verified_user)):
    """
    Charge an authenticated customer using their default payment method.
    
    Retrieves the Stripe customer using the authenticated user's stored Stripe customer ID
    and obtains the default payment method from the customer's invoice settings. Creates a
    payment intent with a predefined amount and metadata that includes the customer's email
    and credits to add. Raises an HTTPException with status code 400 if the user lacks a saved
    Stripe customer ID, does not have a default payment method, or encounters a card error;
    all other exceptions result in an HTTPException with status code 500.
    """
    try:
        if not user.stripe_customer_id:
            raise HTTPException(status_code=400, detail="User does not have a saved Stripe customer ID")

        customer = stripe.Customer.retrieve(user.stripe_customer_id)
        payment_method = customer.get("invoice_settings", {}).get("default_payment_method")

        if not payment_method:
            raise HTTPException(status_code=400, detail="No default payment method found for customer")

        payment_intent = stripe.PaymentIntent.create(
            amount=AMOUNT,
            currency='eur',
            customer=user.stripe_customer_id,
            payment_method=payment_method,
            off_session=True,
            confirm=True,
            metadata={
                "customer_email": user.email,
                "credits_to_add": CREDITS_TO_ADD
            }
        )

        return {"status": "success", "payment_intent": payment_intent}
    except stripe.error.CardError as e:
        raise HTTPException(status_code=400, detail=f"Card error: {e.user_message}")
    except Exception as e:
        print("ERROR:::: ", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/customer-billing-page/")
async def customer_billing_page(user=Depends(get_verified_user)):
    """
    Creates a Stripe Customer Billing Portal session for a verified user.
    
    If the user lacks an associated Stripe customer ID, a new Stripe customer is created and the
    user's record is updated accordingly. A billing portal session is then initiated via Stripe,
    and a dictionary containing the session URL is returned.
    
    Raises:
        HTTPException: If an error occurs while creating the Stripe customer or the billing session.
    """
    test_string = ''
    try:
        test_string += "got user\n"
        if not user.stripe_customer_id:
            test_string += "did not had strip customer id\n"
            data = stripe.Customer.create(
                name=user.name,
                email=user.email,
            )
            user = Users.update_user_by_id(user.id, {"stripe_customer_id": data['id']})
            test_string += "updated the user\n"

        test_string += "fetch user again\n"
        # Create a Customer Portal session
        portal_session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=f"",
        )

        # Return the URL for the billing page
        return {"url": portal_session.url}
    except Exception as e:
        print("ERROR:::: ", e)
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "test_string": test_string,
                "user": user.dict() if user else None,
                "email": user.email
            }
        )

def handle_payment_method_detached(event_data):
    """
    Handles a Stripe payment method detachment event.
    
    Extracts the customer identifier from the event data and uses it to look up the associated user.
    If a user is found, the corresponding company's billing settings are updated by disabling auto-recharge
    and clearing the stored credit card details. Logs messages indicating success or failure.
        
    Args:
        event_data (dict): Dictionary containing event data from Stripe.
    """
    try:
        stripe_customer_id = event_data.get("customer")
        if not stripe_customer_id:
            print("Stripe Customer ID is missing from the event data.")
            return

        user = Users.get_user_by_stripe_customer_id(stripe_customer_id)
        if not user:
            print(f"User not found for Stripe Customer ID: {stripe_customer_id}")
            return

        new_card_number = None
        updated_company = Companies.update_company_by_id(user.company_id, {"auto_recharge": False, "credit_card_number": None})

        if updated_company:
            print(f"Updated card number for company {updated_company.name}: {new_card_number}")
        else:
            print(f"Failed to update card number for customer {stripe_customer_id}")

    except Exception as e:
        print(f"Error handling payment_method.detached: {e}")

def handle_payment_method_attached(event_data):
    """
    Processes a Stripe payment_method.attached event to update company billing details.
    
    If the event data indicates the attachment is from a checkout session, no action is taken.
    Otherwise, the function retrieves the payment method's card details, masks the card number, and
    updates the associated company's credit card information and auto-recharge setting. It also sets
    this payment method as the default for future invoices.
    
    Args:
        event_data (dict): Stripe event payload containing payment method attachment details.
    """
    try:
        # Skip if this is from a checkout session - card details are handled there
        if event_data.get("metadata", {}).get("from_checkout_session"):
            return

        stripe_customer_id = event_data.get("customer")
        if not stripe_customer_id:
            print("Stripe Customer ID is missing from the event data.")
            return

        # Get card details
        payment_method = stripe.PaymentMethod.retrieve(event_data.get("id"))
        if not payment_method or not payment_method.card:
            print("No card details found in payment method.")
            return

        last4 = payment_method.card.last4
        new_card_number = f"**** **** **** {last4}"

        # Find user and update company card details
        user = Users.get_user_by_stripe_customer_id(stripe_customer_id)
        if not user:
            print(f"No user found for Stripe customer ID: {stripe_customer_id}")
            return

        Companies.update_company_by_id(user.company_id, {
            "credit_card_number": new_card_number,
            "auto_recharge": True
        })

        # Set this payment method as the default for future payments
        stripe.Customer.modify(
            stripe_customer_id,
            invoice_settings={
                'default_payment_method': event_data.get("id")
            }
        )

        print(f"Updated card number for company ID {user.company_id}: {new_card_number}")

    except Exception as e:
        print(f"Error handling payment_method.attached: {e}")


class UpdateAutoRechargeRequest(BaseModel):
    auto_recharge: bool

@router.post("/update-auto-recharge/")
async def update_auto_recharge(request: UpdateAutoRechargeRequest, user=Depends(get_verified_user)):
    """
    Update auto-recharge setting for the authenticated user's company.
    
    Enables or disables auto recharge based on the provided request. If enabling auto
    recharge, verifies that the company has a stored credit card; otherwise, raises an
    HTTP 400 error. Attempts to update the company configuration and raises an HTTP 404
    error if the company is not found or the update fails. Any unexpected errors result
    in an HTTP 500 error.
    
    Returns:
        dict: A success message containing the company ID upon successful update.
    """
    try:
        if request.auto_recharge and not Companies.get_company_by_id(user.company_id).credit_card_number:
            raise HTTPException(status_code=400, detail="Auto recharge can only be activated with stored credit card number")

        updated_company = Companies.update_auto_recharge(user.company_id, request.auto_recharge)

        if not updated_company:
            raise HTTPException(status_code=404, detail="Company not found or update failed.")

        return {"message": f"Auto-recharge updated successfully for company {updated_company.id}."}
    except Exception as e:
        print("ERROR:::: ", e)
        raise HTTPException(status_code=500, detail=str(e))
