import json
from pydantic import BaseModel, ConfigDict
from typing import Optional

from sqlalchemy.orm import relationship
from sqlalchemy import String, Column, Integer

from open_webui.internal.db import get_db, Base

############################
# ModelMessageCreditCost DB Schema
############################

class ModelMessageCreditCost(Base):
    __tablename__ = "model_message_credit_cost"

    model_name = Column(String, primary_key=True, unique=True, nullable=False)
    message_credit_cost = Column(Integer, nullable=False)

class ModelMessageCreditCostModel(BaseModel):
    model_name: str
    message_credit_cost: int

    model_config = ConfigDict(from_attributes=True)

############################
# ModelMessageCreditCost Table
############################

class ModelMessageCreditCostTable:
    def get_cost_by_model(self, model_name: str) -> Optional[int]:
        """
        Retrieve the message credit cost for a specified model.
        
        If the model exists in the database, its associated credit cost is returned.
        Returns None if the model is not found or an error occurs.
        
        Args:
            model_name (str): The name of the model to look up.
        
        Returns:
            Optional[int]: The model's message credit cost if found; otherwise, None.
        """
        try:
            with get_db() as db:
                model = db.query(ModelMessageCreditCost).filter_by(model_name=model_name).first()
                return model.message_credit_cost if model else None
        except Exception as e:
            print(f"Error fetching model cost: {e}")
            return None

    def add_model_cost(self, model_name: str, cost: int) -> bool:
        """
        Adds a new model cost record to the database.
        
        Creates a new entry for the provided model name with the specified cost and commits it to the database.
        Returns True if the operation succeeds; otherwise, prints an error and returns False.
        """
        try:
            with get_db() as db:
                model = ModelMessageCreditCost(model_name=model_name, message_credit_cost=cost)
                db.add(model)
                db.commit()
                return True
        except Exception as e:
            print(f"Error adding model cost: {e}")
            return False

    def update_model_cost(self, model_name: str, new_cost: int) -> bool:
        """
        Updates the message credit cost for a given model.
        
        Attempts to update the credit cost associated with the specified model in the
        database. On a successful update, the change is committed and the method returns
        True. In case of an error during the update, an error message is printed and
        False is returned.
        
        Args:
            model_name: The unique identifier of the model to update.
            new_cost: The new credit cost value to assign to the model.
        
        Returns:
            True if the update operation was successful, otherwise False.
        """
        try:
            with get_db() as db:
                db.query(ModelMessageCreditCost).filter_by(model_name=model_name).update({"message_credit_cost": new_cost})
                db.commit()
                return True
        except Exception as e:
            print(f"Error updating model cost: {e}")
            return False

    def delete_model_cost(self, model_name: str) -> bool:
        """
        Deletes the message credit cost record for the specified model.
        
        Attempts to remove the cost entry associated with the given model name from the database.
        Returns True if the deletion and subsequent commit succeed, or False if an error occurs.
            
        Args:
            model_name: The unique identifier of the model whose cost record is to be deleted.
        """
        try:
            with get_db() as db:
                db.query(ModelMessageCreditCost).filter_by(model_name=model_name).delete()
                db.commit()
                return True
        except Exception as e:
            print(f"Error deleting model cost: {e}")
            return False

ModelMessageCreditCosts = ModelMessageCreditCostTable()