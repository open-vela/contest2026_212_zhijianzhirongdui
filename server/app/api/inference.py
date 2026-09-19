"""Inference API router: optional MiMo-VL model analysis endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import get_current_user, optional_current_user, require_permission
from app.models.database import get_db
from app.models.models import Event, User as UserModel
from app.schemas.schemas import ResponseWrapper

router = APIRouter(prefix="/api/inference", tags=["inference"])


@router.post("/analyze")
async def analyze_scene(
    image_b64: str = "",
    prompt: str = "描述这个场景",
    user: UserModel = Depends(get_current_user),
    _=Depends(require_permission("dashboard:view")),
):
    """Analyze a scene image using the vision-language model (MiMo-VL).

    NOTE: Requires Ollama running locally with MiMo-VL. Currently returns
    a placeholder until the model service is fully integrated.
    """
    if not image_b64:
        raise HTTPException(400, detail={"code": "NO_IMAGE", "message": "请提供待分析的图片"})

    # Placeholder — in production this would call Ollama REST API
    return ResponseWrapper(data={
        "activity": "分析请求已接收",
        "detail": f"提示: {prompt}",
        "note": "推理模型服务（MiMo-VL）需额外部署 Ollama",
        "status": "placeholder",
    })


@router.get("/models")
async def list_models(
    user: UserModel = Depends(optional_current_user),
):
    """List available inference models."""
    return ResponseWrapper(data={
        "models": [
            {
                "id": "mimo-vl-miloco:7b-q4_0",
                "name": "MiMo-VL-Miloco 7B (Q4_0)",
                "type": "vision-language",
                "status": "not_connected",
                "endpoint": "http://localhost:11434/api/generate",
            }
        ]
    })
