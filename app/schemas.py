"""Pydantic models for the request and the structured response."""
from typing import List, Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    url: str = Field(..., examples=["https://example.com"])


# ---- LLM output models (lenient defaults so partial output still validates) ----
class Brand(BaseModel):
    name: str = ""
    category: str = ""
    summary: str = ""


class Competitor(BaseModel):
    name: str
    main_service: str = ""
    target_market: str = ""
    strengths: List[str] = []
    weaknesses: List[str] = []
    source: str = "ai_suggested"  # competitors are LLM suggestions, not scraped research


class CompetitorAnalysis(BaseModel):
    brand_overview: str = ""
    main_products_services: List[str] = []
    competitors: List[Competitor] = []
    brand_strengths: List[str] = []
    positioning_opportunities: List[str] = []


class SearchQuery(BaseModel):
    query: str
    platforms: List[str] = []
    intent: str = ""
    business_relevance: str = ""
    target_audience: str = ""


class SEOImprovements(BaseModel):
    primary_keyword: str = ""
    secondary_keywords: List[str] = []
    long_tail_keywords: List[str] = []
    business_keywords: List[str] = []
    recommended_title: str = ""
    meta_description: str = ""
    supporting_content: List[str] = []


class Service(BaseModel):
    name: str
    description: str = ""
    target_industry: str = ""
    target_customer: str = ""
    main_benefit: str = ""
    basis: str = "from_website"  # "from_website" or "inferred"


class TargetAudience(BaseModel):
    primary_audience: List[str] = []
    secondary_audience: List[str] = []
    industries: List[str] = []
    business_types: List[str] = []
    customer_profiles: List[str] = []
    geographic_focus: str = ""
    customer_needs: List[str] = []
    customer_interests: List[str] = []
    recommended_marketing_segments: List[str] = []


class Analysis(BaseModel):
    competitor_analysis: CompetitorAnalysis = CompetitorAnalysis()
    target_search_queries: List[SearchQuery] = []
    seo_improvements: SEOImprovements = SEOImprovements()
    top_services: List[Service] = []
    target_audience: TargetAudience = TargetAudience()


class LLMResult(BaseModel):
    """What we ask the LLM to return."""

    brand: Brand = Brand()
    analysis: Analysis = Analysis()


# ---- API response ----
class Meta(BaseModel):
    provider: str
    model: str
    cached: bool = False
    content_chars_sent: int = 0
    note: str = (
        "Competitors and inferred services are AI-generated suggestions. "
        "No search volume or ranking data is included."
    )


class AnalyzeResponse(BaseModel):
    success: bool = True
    website: str
    brand: Brand
    analysis: Analysis
    meta: Optional[Meta] = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    message: str
