import json
from pydantic import BaseModel, ConfigDict
from typing import Optional

from sqlalchemy.orm import relationship
from sqlalchemy import Integer, String, Column, Text, Boolean

from open_webui.internal.db import get_db, Base

# Constants
NO_COMPANY = "NO_COMPANY"
EIGHTY_PERCENT_CREDIT_LIMIT = 4000

####################
# Company DB Schema
####################

class Company(Base):
    __tablename__ = "company"

    id = Column(String, primary_key=True, unique=True)
    name = Column(String, nullable=False)
    profile_image_url = Column(Text, nullable=True)
    default_model = Column(String, nullable=True)
    allowed_models = Column(Text, nullable=True)
    credit_balance = Column(Integer, default=0)
    auto_recharge = Column(Boolean, default=False)
    credit_card_number = Column(String, nullable=True)

    users = relationship("User", back_populates="company", cascade="all, delete-orphan")

class CompanyModel(BaseModel):
    id: str
    name: str
    profile_image_url: Optional[str] = None
    default_model: Optional[str] = "GPT 4o"
    allowed_models: Optional[str] = None
    credit_balance: Optional[int] = 0
    auto_recharge: Optional[bool] = False
    credit_card_number: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

####################
# Forms
####################

class CompanyModelForm(BaseModel):
    id: str
    model_id: str

class CompanyForm(BaseModel):
    company: dict


class CompanyResponse(BaseModel):
    id: str
    name: str
    profile_image_url: Optional[str] = None
    default_model: Optional[str] = "GPT 4o"
    allowed_models: Optional[str]
    auto_recharge: bool


class CompanyTable:
    def get_company_by_id(self, company_id: str):
        """
        Retrieves a company by its unique identifier.
        
        This method queries the database for a company matching the provided ID and validates the resulting record using CompanyModel.
        If no company is found or an error occurs during retrieval or validation, the method returns None.
        """
        try:
            with get_db() as db:
                company = db.query(Company).filter_by(id=company_id).first()
                return CompanyModel.model_validate(company)
        except Exception as e:
            print(f"Error getting company: {e}")
            return None


    def update_company_by_id(self, id: str, updated: dict) -> Optional[CompanyModel]:
        """
        Updates a company record in the database.
        
        Updates the fields of the company identified by the provided ID using the given values and
        returns a validated company model reflecting the updated state. If an error occurs during the
        process, the function returns None.
        
        Args:
            id: The unique identifier of the company to update.
            updated: A dictionary containing field names and values to update.
            
        Returns:
            A CompanyModel instance with the updated data, or None if the update fails.
        """
        try:
            with get_db() as db:
                db.query(Company).filter_by(id=id).update(updated)
                db.commit()

                company = db.query(Company).filter_by(id=id).first()
                return CompanyModel.model_validate(company)
            
        except Exception as e:
            print(f"Error updating company", e)
            return None


    def update_auto_recharge(self, company_id: str, auto_recharge: bool) -> Optional[CompanyModel]:

        """
        Update the auto-recharge setting for a company.
        
        Updates the auto_recharge field for the company identified by company_id. If the company exists,
        the new auto_recharge state is applied and the updated record is returned as a CompanyModel.
        Returns None if the company is not found or if an error occurs during the update.
        """
        try:
            with get_db() as db:
                company = db.query(Company).filter_by(id=company_id).first()
                if not company:
                    print(f"Company with ID {company_id} not found.")
                    return None

                db.query(Company).filter_by(id=company_id).update({"auto_recharge": auto_recharge})
                db.commit()

                updated_company = db.query(Company).filter_by(id=company_id).first()
                return CompanyModel.model_validate(updated_company)

        except Exception as e:
            print(f"Error updating auto_recharge for company {company_id}: {e}")
            return None


    def get_auto_recharge(self, company_id: str) -> Optional[bool]:
        """
        Retrieves the auto-recharge setting for a company.
        
        Returns the auto-recharge status of the company identified by the given ID. If the company is not found or an error occurs, returns None.
        """
        try:
            with get_db() as db:
                company = db.query(Company).filter_by(id=company_id).first()
                if not company:
                    print(f"Company with ID {company_id} not found.")
                    return None

                return company.auto_recharge

        except Exception as e:
            print(f"Error retrieving auto_recharge for company {company_id}: {e}")
            return None
        
        
    def add_model(self, company_id: str, model_id: str) -> bool:
        """
        Adds a model ID to a company's allowed models list.
        
        Retrieves the company identified by the given company_id and parses its allowed models,
        which are stored as a JSON string. If the company exists and the model_id is not already
        present, the function appends the model_id, updates the database, and returns True.
        If the model_id already exists or an error occurs during the operation, it returns False.
        If no company is found for the given company_id, it returns None.
        """
        try:
            with get_db() as db:
                # Fetch the company by its ID
                company = db.query(Company).filter_by(id=company_id).first()
                print("Company: ", company.allowed_models)
                # If company doesn't exist, return False
                if not company:
                    return None
                
                company.allowed_models = '[]' if company.allowed_models is None else company.allowed_models
                # Load current members from JSON
                current_models = json.loads(company.allowed_models)

                # If model_id is not already in the list, add it
                if model_id not in current_models:
                    current_models.append(model_id)

                    payload = {"allowed_models": json.dumps(current_models)}
                    db.query(Company).filter_by(id=company_id).update(payload)
                    db.commit()

                    return True
                else:
                    # Model already exists in the company
                    return False
        except Exception as e:
            # Handle exceptions if any
            print("ERRRO::: ", e)
            return False

    def remove_model(self, company_id: str, model_id: str) -> bool:
        """
        Removes a model ID from a company's allowed models.
        
        Retrieves the company by its ID and attempts to remove the specified model ID
        from its JSON-encoded list of allowed models. If the model exists in the list,
        the update is committed to the database and the method returns True.
        Returns False if the company is not found, the model ID is not present, or an
        error occurs.
        """
        try:
            with get_db() as db:
                # Fetch the company by its ID
                company = db.query(Company).filter_by(id=company_id).first()
                
                # If company doesn't exist, return False
                if not company:
                    return None
                
                # Load current members from JSON
                current_models = json.loads(company.allowed_models)
                
                # If model_id is in the list, remove it
                if model_id in current_models:
                    current_models.remove(model_id)
                    
                    payload = {"allowed_models": json.dumps(current_models)}
                    db.query(Company).filter_by(id=company_id).update(payload)
                    db.commit()
                    return True
                else:
                    # Member not found in the company
                    return False
        except Exception as e:
            # Handle exceptions if any
            return False

    def update_credit_balance(self, company_id: str, credits_used: int) -> bool:
        """
        Deducts used credits from a company's credit balance.
        
        Queries the database for the company by its identifier. If the company exists and its credit balance is defined, subtracts the specified amount from the balance and commits the change. Returns True if the update is successful; otherwise, returns False.
        """
        with get_db() as db:
            company = db.query(Company).filter(Company.id == company_id).first()
            if company and company.credit_balance is not None:
                company.credit_balance -= credits_used
                db.commit()
                return True
            return False

    def add_credit_balance(self, company_id: str, credits_to_add: int) -> bool:
        """
        Adds the specified number of credits to a company's balance.
        
        Retrieves the company by its identifier and updates its credit balance. If the
        company's current credit balance is undefined, it initializes the balance with
        the provided credits; otherwise, it increments the balance. Commits the change to
        the database. Returns True if the update is successful, or False if no matching
        company is found.
        """
        with get_db() as db:
            company = db.query(Company).filter(Company.id == company_id).first()
            if company:
                if company.credit_balance is None:
                    company.credit_balance = credits_to_add
                else:
                    company.credit_balance += credits_to_add
                db.commit()
                return True
            return False

    def subtract_credit_balance(self, company_id: str, credits_to_subtract: int) -> bool:
        """
        Subtract a specified number of credits from a company's balance.
        
        This method deducts the provided credit amount from the company's current balance if 
        the company exists and has sufficient credits. It commits the change to the database 
        and returns True on a successful deduction; otherwise, it returns False.
        """
        with get_db() as db:
            company = db.query(Company).filter(Company.id == company_id).first()
            if company:
                if company.credit_balance is not None and company.credit_balance >= credits_to_subtract:
                    company.credit_balance -= credits_to_subtract
                    db.commit()
                    return True
            return False

    def get_credit_balance(self, company_id: str) -> Optional[int]:
        """
        Retrieve the current credit balance for a company.
        
        Queries the database for a company with the specified ID and returns its credit balance.
        If no matching company is found, returns None.
        """
        with get_db() as db:
            company = db.query(Company).filter(Company.id == company_id).first()
            return company.credit_balance if company else None

    def create_company(self, company_data: dict) -> Optional[CompanyModel]:
        """
        Creates a new company record using the provided company data.
        
        This method initializes a new company instance with the given attributes, commits
        the new record to the database, refreshes the instance, and returns a validated
        company model. Returns None if an error occurs during the creation process.
        
        Args:
            company_data (dict): A dictionary containing the attributes for the new company.
        
        Returns:
            Optional[CompanyModel]: A validated company model on success; otherwise, None.
        """
        try:
            with get_db() as db:
                company = Company(**company_data)
                db.add(company)
                db.commit()
                db.refresh(company)
                return CompanyModel.model_validate(company)
        except Exception as e:
            print(f"Error creating company: {e}")
            return None

Companies = CompanyTable()