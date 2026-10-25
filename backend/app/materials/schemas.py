from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

MaterialTechGroup = Literal["机械", "硬件", "电控", "算法", "宣运", "通用"]


class MaterialCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    price: str = Field(pattern=r"^(?:0|[1-9]\d{0,9})(?:\.\d{1,2})?$")
    tech_group: MaterialTechGroup
    quantity: int = Field(default=1, ge=1, le=100)
    paired: bool = False
    companion_name: str | None = Field(default=None, max_length=200)
    companion_price: str | None = Field(default=None, pattern=r"^(?:0|[1-9]\d{0,9})(?:\.\d{1,2})?$")
    companion_tech_group: MaterialTechGroup | None = None
    idempotency_key: UUID

    @field_validator("name", "companion_name")
    @classmethod
    def trimmed_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def validate_pair(self) -> "MaterialCreateRequest":
        if not self.name or len(f"{self.name}-{self.quantity}") > 200 and self.quantity > 1:
            raise ValueError("物资名称为空或加编号后超过 200 个字符")
        if self.paired:
            if not self.companion_name or self.companion_name == self.name:
                raise ValueError("配套物品名称不能为空且不能与主物品相同")
            if self.companion_price is None or self.companion_tech_group is None:
                raise ValueError("请填写配套物品价格和技术组")
            if self.quantity > 1 and len(f"{self.companion_name}-{self.quantity}") > 200:
                raise ValueError("配套物品名称加编号后超过 200 个字符")
        elif any((self.companion_name, self.companion_price, self.companion_tech_group)):
            raise ValueError("未启用配套物品时不得提交配套字段")
        return self


class MaterialCreateResponse(BaseModel):
    material_id: UUID
    created_count: int


class MaterialLoanResponse(BaseModel):
    id: UUID
    borrower_user_id: UUID | None
    borrower_name: str
    checked_out_at: datetime
    returned_at: datetime | None
    has_return_photo: bool


class PairedMaterialResponse(BaseModel):
    id: UUID
    name: str
    deleted_at: datetime | None = None


class MaterialListItem(BaseModel):
    id: UUID
    qr_token: UUID
    name: str
    price: str
    tech_group: str
    created_at: datetime
    paired_material: PairedMaterialResponse | None
    active_loan: MaterialLoanResponse | None


class MaterialPage(BaseModel):
    items: list[MaterialListItem]
    page: int
    page_size: int
    total_count: int
    in_use_count: int
    available_count: int
    has_more: bool


class MaterialDetail(MaterialListItem):
    deleted_at: datetime | None
    created_by_user_id: UUID | None
    created_by_name: str
    can_delete: bool
    history: list[MaterialLoanResponse]


class MaterialScanView(MaterialListItem):
    can_return: bool
    can_reclaim: bool


class MaterialScanRequest(BaseModel):
    qr_token: UUID
    operation: Literal["CHECKOUT", "RETURN", "RECLAIM"]
    expected_active_loan_id: UUID | None
    idempotency_key: UUID

    @model_validator(mode="after")
    def validate_expected(self) -> "MaterialScanRequest":
        if (self.operation == "CHECKOUT") != (self.expected_active_loan_id is None):
            raise ValueError("物资状态已变化，请刷新后重试")
        return self


class MaterialScanResponse(BaseModel):
    material_id: UUID
    related_material_ids: list[UUID]
    material_name: str
    operation: Literal["CHECKOUT", "RETURN", "RECLAIM"]
    occurred_at: datetime
