from pydantic import BaseModel, EmailStr, Field

from app.tools.base import execute_tool, with_retries


class CreateLeadInput(BaseModel):
    full_name: str
    company_name: str
    email: EmailStr
    source: str = "outboundos"


class CreateLeadOutput(BaseModel):
    lead_id: str
    status: str


class UpdateLeadInput(BaseModel):
    lead_id: str
    status: str | None = None
    notes: str | None = None
    quality_score: float | None = Field(default=None, ge=0, le=1)


class UpdateLeadOutput(BaseModel):
    lead_id: str
    status: str
    updated_fields: list[str]


@with_retries("create_lead")
async def create_lead(tool_input: CreateLeadInput) -> CreateLeadOutput:
    async def _handler() -> CreateLeadOutput:
        # Placeholder implementation until CRM provider adapter is added.
        lead_id = (
            f"{tool_input.company_name}-{tool_input.full_name}"
            .lower()
            .replace(" ", "-")
            .replace(".", "")
        )
        return CreateLeadOutput(lead_id=lead_id, status="created")

    return await execute_tool("create_lead", _handler)


@with_retries("update_lead")
async def update_lead(tool_input: UpdateLeadInput) -> UpdateLeadOutput:
    async def _handler() -> UpdateLeadOutput:
        # Placeholder implementation until CRM provider adapter is added.
        updated_fields: list[str] = []
        if tool_input.status is not None:
            updated_fields.append("status")
        if tool_input.notes is not None:
            updated_fields.append("notes")
        if tool_input.quality_score is not None:
            updated_fields.append("quality_score")
        status = tool_input.status or "updated"
        return UpdateLeadOutput(
            lead_id=tool_input.lead_id,
            status=status,
            updated_fields=updated_fields,
        )

    return await execute_tool("update_lead", _handler)
