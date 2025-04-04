import logging
import time
from typing import Optional

from .companies import Companies
from open_webui.internal.db import Base, JSONField, get_db
from open_webui.env import SRC_LOG_LEVELS

from beyond_the_loop.models.users import Users

from beyond_the_loop.models.companies import CompanyResponse


from pydantic import BaseModel, ConfigDict

from sqlalchemy import or_, and_, func
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy import BigInteger, Column, Text, JSON, Boolean


from open_webui.utils.access_control import has_access


log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])


####################
# Models DB Schema
####################


# ModelParams is a model for the data stored in the params field of the Model table
class ModelParams(BaseModel):
    model_config = ConfigDict(extra="allow")
    pass


# ModelMeta is a model for the data stored in the meta field of the Model table
class ModelMeta(BaseModel):
    profile_image_url: Optional[str] = "/static/favicon.png"

    description: Optional[str] = None
    """
        User-facing description of the model.
    """

    capabilities: Optional[dict] = None

    model_config = ConfigDict(extra="allow")

    pass


class Model(Base):
    __tablename__ = "model"

    id = Column(Text, primary_key=True)
    """
        The model's id as used in the API. If set to an existing model, it will override the model.
    """

    base_model_id = Column(Text, nullable=True)
    """
        An optional pointer to the actual model that should be used when proxying requests.
    """

    name = Column(Text)
    """
        The human-readable display name of the model.
    """

    params = Column(JSONField)
    """
        Holds a JSON encoded blob of parameters, see `ModelParams`.
    """

    meta = Column(JSONField)
    """
        Holds a JSON encoded blob of metadata, see `ModelMeta`.
    """

    company_id = Column(Text, nullable=False)

    access_control = Column(JSON, nullable=True)  # Controls data access levels.
    # Defines access control rules for this entry.
    # - `None`: Public access, available to all users with the "user" role.
    # - `{}`: Private access, restricted exclusively to the owner.
    # - Custom permissions: Specific access control for reading and writing;
    #   Can specify group or user-level restrictions:
    #   {
    #      "read": {
    #          "group_ids": ["group_id1", "group_id2"],
    #          "user_ids":  ["user_id1", "user_id2"]
    #      },
    #      "write": {
    #          "group_ids": ["group_id1", "group_id2"],
    #          "user_ids":  ["user_id1", "user_id2"]
    #      }
    #   }

    is_active = Column(Boolean, default=True)

    updated_at = Column(BigInteger)
    created_at = Column(BigInteger)


class ModelModel(BaseModel):
    id: str
    base_model_id: Optional[str] = None

    name: str
    params: ModelParams
    meta: ModelMeta

    access_control: Optional[dict] = None

    is_active: bool
    updated_at: int  # timestamp in epoch
    created_at: int  # timestamp in epoch

    company_id: str

    model_config = ConfigDict(from_attributes=True)


####################
# Forms
####################


class ModelCompanyResponse(ModelModel):
    company: Optional[CompanyResponse] = None


class ModelResponse(ModelModel):
    pass


class ModelForm(BaseModel):
    id: str
    base_model_id: Optional[str] = None
    name: str
    meta: ModelMeta
    params: ModelParams
    access_control: Optional[dict] = None
    is_active: bool = True


class ModelsTable:
    def insert_new_model(
        self, form_data: ModelForm, company_id: str
    ) -> Optional[ModelModel]:
        """
        Inserts a new model record into the database.
        
        Constructs a new model using the provided form data and associates it with the
        specified company by setting the company ID and current timestamps. Attempts to
        persist the new record in the database and returns the validated model if successful,
        or None if an error occurs.
            
        Args:
            form_data: A ModelForm instance containing the input data for the model.
            company_id: The identifier for the company associated with the model.
            
        Returns:
            A ModelModel instance representing the new record, or None if insertion fails.
        """
        model = ModelModel(
            **{
                **form_data.model_dump(),
                "company_id": company_id,
                "created_at": int(time.time()),
                "updated_at": int(time.time()),
            }
        )
        try:
            with get_db() as db:
                result = Model(**model.model_dump())
                db.add(result)
                db.commit()
                db.refresh(result)

                if result:
                    return ModelModel.model_validate(result)
                else:
                    return None
        except Exception as e:
            print(e)
            return None

    def get_all_models(self) -> list[ModelModel]:
        """
        Retrieves all models from the database.
        
        Opens a database session, queries all Model records, and validates each record into a
        ModelModel instance. Returns a list of these validated models.
        """
        with get_db() as db:
            return [ModelModel.model_validate(model) for model in db.query(Model).all()]

    def get_models(self) -> list[ModelCompanyResponse]:
        """
        Retrieves models with a base model reference and associated company information.
        
        Queries the database for models with a non-null base_model_id and retrieves the
        corresponding company details using each model's company_id. Returns a list of
        validated ModelCompanyResponse instances.
        """
        with get_db() as db:
            models = []
            for model in db.query(Model).filter(Model.base_model_id != None).all():
                company = Companies.get_company_by_id(model.company_id)
                models.append(
                    ModelCompanyResponse.model_validate(
                        {
                            **ModelModel.model_validate(model).model_dump(),
                            "company": company.model_dump() if company else None,
                        }
                    )
                )
            return models

    def get_base_models(self) -> list[ModelModel]:
        """
        Retrieves all base models from the database.
        
        Queries the Model table for records without an associated base model (i.e. where base_model_id is None) and returns them as validated ModelModel instances.
        """
        with get_db() as db:
            return [
                ModelModel.model_validate(model)
                for model in db.query(Model).filter(Model.base_model_id == None).all()
            ]

    def get_models_by_company_id(
        self, company_id: str, permission: str = "write"
    ) -> list[ModelCompanyResponse]:
        """
        Retrieves models filtered by company ID or access rights.
        
        This function filters the models returned by get_models to include those that either belong to the specified company or for which the company satisfies the required permission level based on the model's access control settings.
        
        Args:
            company_id: The identifier of the company used to filter the models.
            permission: The access permission level required (default is "write").
        
        Returns:
            A list of ModelCompanyResponse instances that match the filtering criteria.
        """
        models = self.get_models()
        return [
            model
            for model in models
            if model.company_id == company_id
            or has_access(company_id, permission, model.access_control)
        ]

    def get_model_by_id(self, id: str) -> Optional[ModelModel]:
        """
        Retrieves a model by its ID from the database.
        
        This method fetches the model corresponding to the provided ID and validates it using ModelModel.
        If no such model is found or an error occurs during retrieval or validation, it returns None.
        """
        try:
            with get_db() as db:
                model = db.get(Model, id)
                return ModelModel.model_validate(model)
        except Exception:
            return None

    def toggle_model_by_id(self, id: str) -> Optional[ModelModel]:
        with get_db() as db:
            try:
                is_active = db.query(Model).filter_by(id=id).first().is_active

                db.query(Model).filter_by(id=id).update(
                    {
                        "is_active": not is_active,
                        "updated_at": int(time.time()),
                    }
                )
                db.commit()

                return self.get_model_by_id(id)
            except Exception:
                return None

    def update_model_by_id(self, id: str, model: ModelForm) -> Optional[ModelModel]:
        try:
            with get_db() as db:
                # update only the fields that are present in the model
                result = (
                    db.query(Model)
                    .filter_by(id=id)
                    .update(model.model_dump(exclude={"id"}))
                )
                db.commit()

                model = db.get(Model, id)
                db.refresh(model)
                return ModelModel.model_validate(model)
        except Exception as e:
            print(e)

            return None

    def delete_model_by_id(self, id: str) -> bool:
        try:
            with get_db() as db:
                db.query(Model).filter_by(id=id).delete()
                db.commit()

                return True
        except Exception:
            return False

    def delete_all_models(self) -> bool:
        try:
            with get_db() as db:
                db.query(Model).delete()
                db.commit()

                return True
        except Exception:
            return False


Models = ModelsTable()
