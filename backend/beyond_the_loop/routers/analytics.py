from datetime import datetime, timedelta

from fastapi import HTTPException, Depends
from fastapi.params import Query

from open_webui.internal.db import get_db
from beyond_the_loop.models.completions import Completion
from beyond_the_loop.models.users import User

from sqlalchemy import func

from fastapi import APIRouter

import logging

from open_webui.env import SRC_LOG_LEVELS
from open_webui.utils.auth import get_verified_user

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

router = APIRouter()

@router.get("/top-models")
async def get_top_models(
    start_date: str = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(None, description="End date in YYYY-MM-DD format"),
    user=Depends(get_verified_user)
):
    """
    Retrieves the top 3 models by usage for the verified user within a specified date range.
    
    The start date must be provided in YYYY-MM-DD format. The end date is optional and defaults to the current date.
    The function aggregates completion records by model, returning a list of dictionaries with each model and its usage count,
    or a message if no data is available.
    
    Raises:
        HTTPException: If the start date is missing, if the start date is after the end date, or if the date format is invalid.
        HTTPException: For any other errors encountered during data retrieval.
    """
    try:
        if start_date:
            start_date_dt = datetime.strptime(start_date, "%Y-%m-%d")
            start_timestamp = int(start_date_dt.timestamp())
        else:
            raise HTTPException(status_code=400, detail="Start date is required.")

        if end_date:
            end_date_dt = datetime.strptime(end_date, "%Y-%m-%d")
            end_timestamp = int(end_date_dt.timestamp())
        else:
            end_date_dt = datetime.now()
            end_timestamp = int(end_date_dt.timestamp())

        if start_timestamp > end_timestamp:
            raise HTTPException(status_code=400, detail="Start date must be before end date.")

        with get_db() as db:
            query = db.query(
                Completion.model,
                func.count(Completion.id).label("usage_count")
            ).filter(
                Completion.created_at >= start_timestamp,
                Completion.created_at <= end_timestamp
            )

            query = query.filter(Completion.user_id == user.id)

            top_models = query.group_by(Completion.model).order_by(func.count(Completion.id).desc()).limit(3).all()

        if not top_models:
            return {"message": "No data found for the given parameters."}

        return [{"model": model, "usage_count": count} for model, count in top_models]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching top models: {e}")


@router.get("/top-users")
async def get_top_users(
    start_date: str = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(None, description="End date in YYYY-MM-DD format"),
    user=Depends(get_verified_user)
):
    """
    Fetches the top 3 users with the highest token usage for the user's company within a specified date range.
    
    The start_date parameter is required and must be in "YYYY-MM-DD" format. If end_date is not provided,
    the current date and time is used. The function aggregates token usage for completions made between the
    specified dates and returns a list of dictionaries containing user details and total credits used.
    
    Returns:
        List[dict]: A list where each dictionary contains:
            - user_id: Unique identifier of the user.
            - name: The user's name.
            - email: The user's email address.
            - profile_image_url: URL to the user's profile image.
            - total_credits_used: Total token usage for the user.
    
    Raises:
        HTTPException: If start_date is missing, the date format is invalid, or start_date is after end_date.
        HTTPException: For any general error encountered during data retrieval.
    """
    try:
        if start_date:
            start_date_dt = datetime.strptime(start_date, "%Y-%m-%d")
            start_timestamp = int(start_date_dt.timestamp())
        else:
            raise HTTPException(status_code=400, detail="Start date is required.")

        if end_date:
            end_date_dt = datetime.strptime(end_date, "%Y-%m-%d")
            end_timestamp = int(end_date_dt.timestamp())
        else:
            end_date_dt = datetime.now()
            end_timestamp = int(end_date_dt.timestamp())

        if start_timestamp > end_timestamp:
            raise HTTPException(status_code=400, detail="Start date must be before end date.")

        with get_db() as db:
            top_users = db.query(
                Completion.user_id,
                func.sum(Completion.credits_used).label("total_credits"),
                User.name,
                User.email,
                User.profile_image_url
            ).join(
                User, User.id == Completion.user_id
            ).filter(
                Completion.created_at >= start_timestamp,
                Completion.created_at <= end_timestamp,
            ).group_by(
                Completion.user_id, User.name, User.email, User.profile_image_url
            ).order_by(
                func.sum(Completion.credits_used).desc()
            ).limit(3).all()

        return [
            {
                "user_id": user_id,
                "name": name,
                "email": email,
                "profile_image_url": profile_image_url,
                "total_credits_used": total_credits
            }
            for user_id, total_credits, name, email, profile_image_url in top_users
        ]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching top users: {e}")


@router.get("/stats/total-billing")
async def get_total_billing(
    start_date: str = Query(None, description="Start date in YYYY-MM-DD format (optional)"),
    end_date: str = Query(None, description="End date in YYYY-MM-DD format (optional)"),
    user=Depends(get_verified_user)
):
    """
    Retrieves total billing data with month-over-month percentage changes.
    
    This endpoint aggregates billing information from completions records for the
    authenticated user's company, grouped by month. If start_date and end_date are
    not provided, billing data is computed for the period from one year ago to the
    current date. The monthly totals are calculated by summing credits used, and a
    percentage change relative to the previous month is computed, with "N/A" denoting
    an unavailable comparison.
    
    Raises:
        HTTPException: If the start_date is after the end_date or if the provided dates
        are not in the required YYYY-MM-DD format (HTTP 400), or if an error occurs while
        fetching data (HTTP 500).
    
    Returns:
        A dictionary with two keys:
            - "monthly_billing": A mapping of month (YYYY-MM) to the total billing amount.
            - "percentage_changes": A mapping of month (YYYY-MM) to the month-over-month 
              billing change percentage.
    """
    try:
        current_date = datetime.now()
        one_year_ago = current_date.replace(day=1) - timedelta(days=365)

        # Parse start_date
        if start_date:
            start_date_dt = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start_date_dt = one_year_ago  # Default to one year ago

        # Parse end_date
        if end_date:
            end_date_dt = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            end_date_dt = current_date  # Default to current date

        if start_date_dt > end_date_dt:
            raise HTTPException(status_code=400, detail="Start date must be before end date.")

        # Ensure end_date includes the entire day
        end_date_dt = end_date_dt.replace(hour=23, minute=59, second=59)

        with get_db() as db:
            query = db.query(
                func.strftime('%Y-%m', func.datetime(Completion.created_at, 'unixepoch')).label("month"),
                func.sum(Completion.credits_used).label("total_billing")
            ).filter(
                func.datetime(Completion.created_at, 'unixepoch') >= start_date_dt.strftime('%Y-%m-%d 00:00:00'),
                func.datetime(Completion.created_at, 'unixepoch') <= end_date_dt.strftime('%Y-%m-%d %H:%M:%S')
            )

            query = query.filter(Completion.user_id == user.id)

            # Execute the query and fetch results
            results = query.group_by("month").order_by("month").all()

            # Convert results to a dictionary
            monthly_billing = {row[0]: float(row[1]) for row in results}

        # Generate all months within the specified range
        months = []
        current_month = start_date_dt.replace(day=1)
        end_month = end_date_dt.replace(day=1)

        while current_month <= end_month:
            months.append(current_month.strftime('%Y-%m'))
            # Move to the first day of next month
            if current_month.month == 12:
                current_month = current_month.replace(year=current_month.year + 1, month=1)
            else:
                current_month = current_month.replace(month=current_month.month + 1)

        billing_data = {month: monthly_billing.get(month, 0) for month in months}

        # Calculate percentage changes month-over-month
        percentage_changes = {}
        previous_value = None
        for month, value in billing_data.items():
            if previous_value is not None:
                change = ((value - previous_value) / previous_value) * 100 if previous_value != 0 else None
                percentage_changes[month] = round(change, 2) if change is not None else "N/A"
            else:
                percentage_changes[month] = "N/A"
            previous_value = value

        return {
            "monthly_billing": billing_data,
            "percentage_changes": percentage_changes
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching billing stats: {e}")


@router.get("/stats/total-messages")
async def get_total_messages(
    start_date: str = Query(None, description="Start date in YYYY-MM-DD format (optional)"),
    end_date: str = Query(None, description="End date in YYYY-MM-DD format (optional)"),
    user=Depends(get_verified_user)
):
    """
    Retrieve monthly message completions and month-over-month percentage changes.
    
    Aggregates the total number of completions per month for the user's company over a specified
    date range. If no dates are provided, defaults to the past 12 months ending on the current date.
    Also computes the percentage change in completions compared to the previous month. The returned
    dictionary contains:
      - "monthly_messages": Mapping of month (YYYY-MM) to the total completions.
      - "percentage_changes": Mapping of month to its percentage change from the preceding month.
    
    Raises:
        HTTPException: For invalid date formats, when the start date is later than the end date, or if
                       an error occurs during data retrieval.
    """
    try:
        current_date = datetime.now()
        one_year_ago = current_date.replace(day=1) - timedelta(days=365)

        # Parse start_date
        if start_date:
            start_date_dt = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start_date_dt = one_year_ago  # Default to one year ago

        # Parse end_date
        if end_date:
            end_date_dt = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            end_date_dt = current_date  # Default to current date

        if start_date_dt > end_date_dt:
            raise HTTPException(status_code=400, detail="Start date must be before end date.")

        # Ensure end_date includes the entire day
        end_date_dt = end_date_dt.replace(hour=23, minute=59, second=59)

        with get_db() as db:
            query = db.query(
                func.strftime('%Y-%m', func.datetime(Completion.created_at, 'unixepoch')).label("month"),
                func.count(Completion.id).label("total_messages")
            ).filter(
                func.datetime(Completion.created_at, 'unixepoch') >= start_date_dt.strftime('%Y-%m-%d 00:00:00'),
                func.datetime(Completion.created_at, 'unixepoch') <= end_date_dt.strftime('%Y-%m-%d %H:%M:%S')
            )

            query = query.filter(Completion.user_id == user.id)

            # Execute the query and fetch results
            results = query.group_by("month").order_by("month").all()

            # Convert results to a dictionary
            monthly_messages = {row[0]: int(row[1]) for row in results}

        # Generate all months within the specified range
        months = []
        current_month = start_date_dt.replace(day=1)
        end_month = end_date_dt.replace(day=1)

        while current_month <= end_month:
            months.append(current_month.strftime('%Y-%m'))
            # Move to the first day of next month
            if current_month.month == 12:
                current_month = current_month.replace(year=current_month.year + 1, month=1)
            else:
                current_month = current_month.replace(month=current_month.month + 1)

        message_data = {month: monthly_messages.get(month, 0) for month in months}

        # Calculate percentage changes month-over-month
        percentage_changes = {}
        previous_value = None
        for month, value in message_data.items():
            if previous_value is not None:
                change = ((value - previous_value) / previous_value) * 100 if previous_value != 0 else None
                percentage_changes[month] = round(change, 2) if change is not None else "N/A"
            else:
                percentage_changes[month] = "N/A"
            previous_value = value

        return {
            "monthly_messages": message_data,
            "percentage_changes": percentage_changes
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching message stats: {e}")


@router.get("/stats/total-chats")
async def get_total_chats(
    start_date: str = Query(None, description="Start date in YYYY-MM-DD format (optional)"),
    end_date: str = Query(None, description="End date in YYYY-MM-DD format (optional)"),
    user=Depends(get_verified_user)
):
    """
    Return monthly unique chat counts and month-over-month percentage changes.
    
    This function aggregates unique chat counts by month for the authenticated user within a
    specified date range. If no dates are provided, it defaults to the last 12 months. In
    addition to the monthly counts, it computes the percentage change relative to the previous
    month for each interval.
    
    Args:
        start_date (str, optional): Start date in "YYYY-MM-DD" format. Defaults to one year ago.
        end_date (str, optional): End date in "YYYY-MM-DD" format. Defaults to the current date.
    
    Returns:
        dict: A dictionary containing:
            - "monthly_chats": A mapping of month (formatted as "YYYY-MM") to the count of unique chats.
            - "percentage_changes": A mapping of month to the percentage change from the previous month.
    
    Raises:
        HTTPException: If the date format is invalid, if the start date is after the end date, or if
                       an error occurs during data retrieval.
    """
    try:
        current_date = datetime.now()
        one_year_ago = current_date.replace(day=1) - timedelta(days=365)

        # Parse start_date
        if start_date:
            start_date_dt = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start_date_dt = one_year_ago  # Default to one year ago

        # Parse end_date
        if end_date:
            end_date_dt = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            end_date_dt = current_date  # Default to current date

        if start_date_dt > end_date_dt:
            raise HTTPException(status_code=400, detail="Start date must be before end date.")

        # Ensure end_date includes the entire day
        end_date_dt = end_date_dt.replace(hour=23, minute=59, second=59)

        with get_db() as db:
            query = db.query(
                func.strftime('%Y-%m', func.datetime(Completion.created_at, 'unixepoch')).label("month"),
                func.count(func.distinct(Completion.chat_id)).label("total_chats")
            ).filter(
                func.datetime(Completion.created_at, 'unixepoch') >= start_date_dt.strftime('%Y-%m-%d 00:00:00'),
                func.datetime(Completion.created_at, 'unixepoch') <= end_date_dt.strftime('%Y-%m-%d %H:%M:%S')
            )

            query = query.filter(Completion.user_id == user.id)

            # Execute the query and fetch results
            results = query.group_by("month").order_by("month").all()

            # Convert results to a dictionary
            monthly_chats = {row[0]: int(row[1]) for row in results}

        # Generate all months within the specified range
        months = []
        current_month = start_date_dt.replace(day=1)
        end_month = end_date_dt.replace(day=1)

        while current_month <= end_month:
            months.append(current_month.strftime('%Y-%m'))
            # Move to the first day of next month
            if current_month.month == 12:
                current_month = current_month.replace(year=current_month.year + 1, month=1)
            else:
                current_month = current_month.replace(month=current_month.month + 1)

        chat_data = {month: monthly_chats.get(month, 0) for month in months}

        # Calculate percentage changes month-over-month
        percentage_changes = {}
        previous_value = None
        for month, value in chat_data.items():
            if previous_value is not None:
                change = ((value - previous_value) / previous_value) * 100 if previous_value != 0 else None
                percentage_changes[month] = round(change, 2) if change is not None else "N/A"
            else:
                percentage_changes[month] = "N/A"
            previous_value = value

        return {
            "monthly_chats": chat_data,
            "percentage_changes": percentage_changes
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching chat stats: {e}")


@router.get("/stats/saved-time-in-seconds")
async def get_saved_time_in_seconds(
    start_date: str = Query(None, description="Start date in YYYY-MM-DD format (optional)"),
    end_date: str = Query(None, description="End date in YYYY-MM-DD format (optional)"),
    user=Depends(get_verified_user)
):
    """
    Retrieves monthly saved time statistics and percentage changes.
    
    Aggregates the total saved time in seconds from the authenticated user's completions,
    grouping the results by month for a specified date range (defaults to the last 12 months).
    The endpoint calculates the monthly total saved time and the percentage change relative
    to the previous month. Dates must be in YYYY-MM-DD format with start_date preceding end_date.
    Raises HTTPException for invalid date formats or when start_date is after end_date.
    """
    try:
        current_date = datetime.now()
        one_year_ago = current_date.replace(day=1) - timedelta(days=365)

        # Parse start_date
        if start_date:
            start_date_dt = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start_date_dt = one_year_ago  # Default to one year ago

        # Parse end_date
        if end_date:
            end_date_dt = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            end_date_dt = current_date  # Default to current date

        if start_date_dt > end_date_dt:
            raise HTTPException(status_code=400, detail="Start date must be before end date.")

        # Ensure end_date includes the entire day
        end_date_dt = end_date_dt.replace(hour=23, minute=59, second=59)

        with get_db() as db:
            query = db.query(
                func.strftime('%Y-%m', func.datetime(Completion.created_at, 'unixepoch')).label("month"),
                func.sum(Completion.time_saved_in_seconds).label("total_saved_time")
            ).filter(
                func.datetime(Completion.created_at, 'unixepoch') >= start_date_dt.strftime('%Y-%m-%d 00:00:00'),
                func.datetime(Completion.created_at, 'unixepoch') <= end_date_dt.strftime('%Y-%m-%d %H:%M:%S')
            )

            query = query.filter(Completion.user_id == user.id)

            # Execute the query and fetch results
            results = query.group_by("month").order_by("month").all()

            # Convert results to a dictionary
            monthly_saved_time = {row[0]: int(row[1]) if row[1] is not None else 0 for row in results}

        # Generate all months within the specified range
        months = []
        current_month = start_date_dt.replace(day=1)
        end_month = end_date_dt.replace(day=1)

        while current_month <= end_month:
            months.append(current_month.strftime('%Y-%m'))
            # Move to the first day of next month
            if current_month.month == 12:
                current_month = current_month.replace(year=current_month.year + 1, month=1)
            else:
                current_month = current_month.replace(month=current_month.month + 1)

        saved_time_data = {month: monthly_saved_time.get(month, 0) for month in months}

        # Calculate percentage changes month-over-month
        percentage_changes = {}
        previous_value = None
        for month, value in saved_time_data.items():
            if previous_value is not None:
                change = ((value - previous_value) / previous_value) * 100 if previous_value != 0 else None
                percentage_changes[month] = round(change, 2) if change is not None else "N/A"
            else:
                percentage_changes[month] = "N/A"
            previous_value = value

        return {
            "monthly_saved_time_in_seconds": saved_time_data,
            "percentage_changes": percentage_changes
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching saved time stats: {e}")
