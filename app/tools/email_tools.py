from pydantic import BaseModel, Field

from app.tools.base import execute_tool, with_retries


class ValidateEmailLengthInput(BaseModel):
    email_body: str
    min_chars: int = 50
    max_chars: int = 1200


class ValidateEmailLengthOutput(BaseModel):
    char_count: int
    is_valid: bool
    reason: str


class DetectHallucinationsInput(BaseModel):
    email_body: str
    known_facts: list[str]


class DetectHallucinationsOutput(BaseModel):
    hallucination_detected: bool
    unsupported_claims: list[str]


class ExtractCompanyFactsInput(BaseModel):
    company_summary: str
    max_facts: int = Field(default=5, ge=1, le=20)


class ExtractCompanyFactsOutput(BaseModel):
    facts: list[str]


@with_retries("validate_email_length")
async def validate_email_length(tool_input: ValidateEmailLengthInput) -> ValidateEmailLengthOutput:
    async def _handler() -> ValidateEmailLengthOutput:
        char_count = len(tool_input.email_body)
        is_valid = tool_input.min_chars <= char_count <= tool_input.max_chars
        if is_valid:
            reason = "Email length is within configured boundaries"
        else:
            reason = "Email length is outside configured boundaries"
        return ValidateEmailLengthOutput(char_count=char_count, is_valid=is_valid, reason=reason)

    return await execute_tool("validate_email_length", _handler)


@with_retries("detect_hallucinations")
async def detect_hallucinations(
    tool_input: DetectHallucinationsInput,
) -> DetectHallucinationsOutput:
    async def _handler() -> DetectHallucinationsOutput:
        known_fact_tokens = [fact.lower() for fact in tool_input.known_facts]
        unsupported_claims = [
            sentence.strip()
            for sentence in tool_input.email_body.split(".")
            if sentence.strip()
            and known_fact_tokens
            and not any(token in sentence.lower() for token in known_fact_tokens)
        ]
        hallucination_detected = len(unsupported_claims) > 0
        return DetectHallucinationsOutput(
            hallucination_detected=hallucination_detected,
            unsupported_claims=unsupported_claims,
        )

    return await execute_tool("detect_hallucinations", _handler)


@with_retries("extract_company_facts")
async def extract_company_facts(tool_input: ExtractCompanyFactsInput) -> ExtractCompanyFactsOutput:
    async def _handler() -> ExtractCompanyFactsOutput:
        facts = [
            fragment.strip()
            for fragment in tool_input.company_summary.split(".")
            if fragment.strip()
        ][: tool_input.max_facts]
        return ExtractCompanyFactsOutput(facts=facts)

    return await execute_tool("extract_company_facts", _handler)
