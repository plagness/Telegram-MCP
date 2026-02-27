"""Handler для governance (Democracy) — proxy к democracycore."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..config import get_settings
from . import (
    PageTypeHandler,
    proxy_delete,
    proxy_get,
    proxy_post,
    validate_page_request,
)

logger = logging.getLogger(__name__)
settings = get_settings()

_PAGE_TYPE = "governance"


class GovernanceHandler(PageTypeHandler):
    """Democracy: голосования, предложения, казна, конституция."""

    page_type = _PAGE_TYPE
    template = "governance.html"
    scripts = ["echarts"]

    def register_routes(self, router: APIRouter) -> None:
        """Proxy-маршруты к democracycore."""

        @router.get(f"/p/{{slug}}/{_PAGE_TYPE}/data")
        async def governance_data_proxy(slug: str, request: Request):
            """Данные governance/dashboard из Democracy."""
            page, _user = await validate_page_request(slug, _PAGE_TYPE, request)

            init_data = request.headers.get("X-Init-Data", "")
            chat_id = (page.get("config") or {}).get("chat_id", "")
            if not chat_id:
                raise HTTPException(status_code=400, detail="chat_id not configured")

            headers = {"X-Init-Data": init_data} if init_data else {}
            return await proxy_get(
                f"{settings.democracy_url}/v1/dashboard/{chat_id}",
                headers=headers,
            )

        @router.post(f"/p/{{slug}}/{_PAGE_TYPE}/vote")
        async def governance_vote_proxy(slug: str, request: Request):
            """Голосование через Democracy."""
            page, _user = await validate_page_request(slug, _PAGE_TYPE, request)
            init_data = request.headers.get("X-Init-Data", "")
            if not init_data:
                raise HTTPException(status_code=401, detail="initData required")

            body = await request.json()
            proposal_id = body.get("proposal_id")
            if not proposal_id:
                raise HTTPException(status_code=400, detail="proposal_id required")

            return await proxy_post(
                f"{settings.democracy_url}/v1/proposals/{proposal_id}/vote",
                json_body={"choice": body.get("choice", "")},
                headers={"X-Init-Data": init_data},
            )

        @router.delete(f"/p/{{slug}}/{_PAGE_TYPE}/vote")
        async def governance_vote_delete_proxy(slug: str, request: Request):
            """Отмена голоса через Democracy."""
            page, _user = await validate_page_request(slug, _PAGE_TYPE, request)
            init_data = request.headers.get("X-Init-Data", "")
            if not init_data:
                raise HTTPException(status_code=401, detail="initData required")

            body = await request.json()
            proposal_id = body.get("proposal_id")
            if not proposal_id:
                raise HTTPException(status_code=400, detail="proposal_id required")

            return await proxy_delete(
                f"{settings.democracy_url}/v1/proposals/{proposal_id}/vote",
                headers={"X-Init-Data": init_data},
            )

        @router.get(f"/p/{{slug}}/{_PAGE_TYPE}/proposal/{{proposal_id}}")
        async def governance_proposal_detail_proxy(
            slug: str, proposal_id: int, request: Request
        ):
            """Детали предложения с аргументами и голосом пользователя."""
            await validate_page_request(slug, _PAGE_TYPE, request)
            init_data = request.headers.get("X-Init-Data", "")
            headers = {"X-Init-Data": init_data} if init_data else {}
            return await proxy_get(
                f"{settings.democracy_url}/v1/proposals/{proposal_id}",
                headers=headers,
            )

        @router.post(f"/p/{{slug}}/{_PAGE_TYPE}/argument")
        async def governance_argument_proxy(slug: str, request: Request):
            """Добавление аргумента через Democracy."""
            await validate_page_request(slug, _PAGE_TYPE, request)
            init_data = request.headers.get("X-Init-Data", "")
            if not init_data:
                raise HTTPException(status_code=401, detail="initData required")

            body = await request.json()
            proposal_id = body.get("proposal_id")
            if not proposal_id:
                raise HTTPException(status_code=400, detail="proposal_id required")

            return await proxy_post(
                f"{settings.democracy_url}/v1/proposals/{proposal_id}/arguments",
                json_body={"side": body.get("side", ""), "text": body.get("text", "")},
                headers={"X-Init-Data": init_data},
            )

        @router.post(f"/p/{{slug}}/{_PAGE_TYPE}/proposal")
        async def governance_create_proxy(slug: str, request: Request):
            """Создание предложения через Democracy."""
            await validate_page_request(slug, _PAGE_TYPE, request)
            init_data = request.headers.get("X-Init-Data", "")
            if not init_data:
                raise HTTPException(status_code=401, detail="initData required")

            body = await request.json()
            return await proxy_post(
                f"{settings.democracy_url}/v1/proposals",
                json_body=body,
                headers={"X-Init-Data": init_data},
            )

        @router.post(f"/p/{{slug}}/{_PAGE_TYPE}/setup")
        async def governance_setup_proxy(slug: str, request: Request):
            """Установка режима правления через Democracy."""
            page, _user = await validate_page_request(slug, _PAGE_TYPE, request)
            init_data = request.headers.get("X-Init-Data", "")
            if not init_data:
                raise HTTPException(status_code=401, detail="initData required")

            body = await request.json()
            chat_id = (page.get("config") or {}).get("chat_id", "")
            if not chat_id:
                raise HTTPException(status_code=400, detail="chat_id not configured")

            return await proxy_post(
                f"{settings.democracy_url}/v1/governance/{chat_id}/setup",
                json_body=body,
                headers={"X-Init-Data": init_data},
            )

        @router.post(f"/p/{{slug}}/{_PAGE_TYPE}/change-regime")
        async def governance_change_regime_proxy(slug: str, request: Request):
            """Смена режима правления через Democracy."""
            page, _user = await validate_page_request(slug, _PAGE_TYPE, request)
            init_data = request.headers.get("X-Init-Data", "")
            if not init_data:
                raise HTTPException(status_code=401, detail="initData required")

            body = await request.json()
            chat_id = (page.get("config") or {}).get("chat_id", "")
            if not chat_id:
                raise HTTPException(status_code=400, detail="chat_id not configured")

            return await proxy_post(
                f"{settings.democracy_url}/v1/governance/{chat_id}/change-regime",
                json_body=body,
                headers={"X-Init-Data": init_data},
            )

        @router.post(f"/p/{{slug}}/{_PAGE_TYPE}/sync")
        async def governance_sync_proxy(slug: str, request: Request):
            """Синхронизация участников чата через Democracy."""
            page, _user = await validate_page_request(slug, _PAGE_TYPE, request)
            init_data = request.headers.get("X-Init-Data", "")
            if not init_data:
                raise HTTPException(status_code=401, detail="initData required")

            chat_id = (page.get("config") or {}).get("chat_id", "")
            if not chat_id:
                raise HTTPException(status_code=400, detail="chat_id not configured")

            return await proxy_post(
                f"{settings.democracy_url}/v1/governance/{chat_id}/sync",
                json_body=None,
                headers={"X-Init-Data": init_data},
                timeout=15.0,
            )

        # === Council ===
        @router.get(f"/p/{{slug}}/{_PAGE_TYPE}/council")
        async def governance_council_proxy(slug: str, request: Request):
            """Список членов совета."""
            page, _user = await validate_page_request(slug, _PAGE_TYPE, request)
            init_data = request.headers.get("X-Init-Data", "")
            chat_id = (page.get("config") or {}).get("chat_id", "")
            if not chat_id:
                raise HTTPException(status_code=400, detail="chat_id not configured")
            headers = {"X-Init-Data": init_data} if init_data else {}
            return await proxy_get(
                f"{settings.democracy_url}/v1/council/{chat_id}",
                headers=headers,
            )

        # === Petitions ===
        @router.post(f"/p/{{slug}}/{_PAGE_TYPE}/petition")
        async def governance_create_petition_proxy(slug: str, request: Request):
            """Создание петиции."""
            page, _user = await validate_page_request(slug, _PAGE_TYPE, request)
            init_data = request.headers.get("X-Init-Data", "")
            if not init_data:
                raise HTTPException(status_code=401, detail="initData required")
            chat_id = (page.get("config") or {}).get("chat_id", "")
            if not chat_id:
                raise HTTPException(status_code=400, detail="chat_id not configured")
            body = await request.json()
            return await proxy_post(
                f"{settings.democracy_url}/v1/petitions/{chat_id}",
                json_body=body,
                headers={"X-Init-Data": init_data},
            )

        @router.get(f"/p/{{slug}}/{_PAGE_TYPE}/petitions")
        async def governance_list_petitions_proxy(slug: str, request: Request):
            """Список петиций."""
            page, _user = await validate_page_request(slug, _PAGE_TYPE, request)
            init_data = request.headers.get("X-Init-Data", "")
            chat_id = (page.get("config") or {}).get("chat_id", "")
            if not chat_id:
                raise HTTPException(status_code=400, detail="chat_id not configured")
            headers = {"X-Init-Data": init_data} if init_data else {}
            qs = request.url.query
            url = f"{settings.democracy_url}/v1/petitions/{chat_id}"
            if qs:
                url += f"?{qs}"
            return await proxy_get(url, headers=headers)

        @router.post(f"/p/{{slug}}/{_PAGE_TYPE}/petition/{{petition_id}}/sign")
        async def governance_sign_petition_proxy(
            slug: str, petition_id: int, request: Request
        ):
            """Подписать петицию."""
            page, _user = await validate_page_request(slug, _PAGE_TYPE, request)
            init_data = request.headers.get("X-Init-Data", "")
            if not init_data:
                raise HTTPException(status_code=401, detail="initData required")
            chat_id = (page.get("config") or {}).get("chat_id", "")
            if not chat_id:
                raise HTTPException(status_code=400, detail="chat_id not configured")
            return await proxy_post(
                f"{settings.democracy_url}/v1/petitions/{chat_id}/{petition_id}/sign",
                json_body=None,
                headers={"X-Init-Data": init_data},
            )

        @router.get(f"/p/{{slug}}/{_PAGE_TYPE}/petition/{{petition_id}}")
        async def governance_get_petition_proxy(
            slug: str, petition_id: int, request: Request
        ):
            """Детали петиции."""
            page, _user = await validate_page_request(slug, _PAGE_TYPE, request)
            init_data = request.headers.get("X-Init-Data", "")
            chat_id = (page.get("config") or {}).get("chat_id", "")
            if not chat_id:
                raise HTTPException(status_code=400, detail="chat_id not configured")
            headers = {"X-Init-Data": init_data} if init_data else {}
            return await proxy_get(
                f"{settings.democracy_url}/v1/petitions/{chat_id}/{petition_id}",
                headers=headers,
            )

        # === Delegations (Liquid Democracy) ===
        @router.post(f"/p/{{slug}}/{_PAGE_TYPE}/delegate")
        async def governance_create_delegation_proxy(slug: str, request: Request):
            """Делегировать голос."""
            page, _user = await validate_page_request(slug, _PAGE_TYPE, request)
            init_data = request.headers.get("X-Init-Data", "")
            if not init_data:
                raise HTTPException(status_code=401, detail="initData required")
            chat_id = (page.get("config") or {}).get("chat_id", "")
            if not chat_id:
                raise HTTPException(status_code=400, detail="chat_id not configured")
            body = await request.json()
            return await proxy_post(
                f"{settings.democracy_url}/v1/delegations/{chat_id}",
                json_body=body,
                headers={"X-Init-Data": init_data},
            )

        @router.delete(f"/p/{{slug}}/{_PAGE_TYPE}/delegate")
        async def governance_delete_delegation_proxy(slug: str, request: Request):
            """Отозвать делегирование."""
            page, _user = await validate_page_request(slug, _PAGE_TYPE, request)
            init_data = request.headers.get("X-Init-Data", "")
            if not init_data:
                raise HTTPException(status_code=401, detail="initData required")
            chat_id = (page.get("config") or {}).get("chat_id", "")
            if not chat_id:
                raise HTTPException(status_code=400, detail="chat_id not configured")
            body = await request.json()
            qs = "&".join(f"{k}={v}" for k, v in body.items())
            url = f"{settings.democracy_url}/v1/delegations/{chat_id}"
            if qs:
                url += f"?{qs}"
            return await proxy_delete(
                url,
                headers={"X-Init-Data": init_data},
            )

        @router.get(f"/p/{{slug}}/{_PAGE_TYPE}/delegations")
        async def governance_list_delegations_proxy(slug: str, request: Request):
            """Мои делегирования."""
            page, _user = await validate_page_request(slug, _PAGE_TYPE, request)
            init_data = request.headers.get("X-Init-Data", "")
            if not init_data:
                raise HTTPException(status_code=401, detail="initData required")
            chat_id = (page.get("config") or {}).get("chat_id", "")
            if not chat_id:
                raise HTTPException(status_code=400, detail="chat_id not configured")
            return await proxy_get(
                f"{settings.democracy_url}/v1/delegations/{chat_id}",
                headers={"X-Init-Data": init_data},
            )

        @router.get(f"/p/{{slug}}/{_PAGE_TYPE}/voting-power/{{user_id}}")
        async def governance_voting_power_proxy(
            slug: str, user_id: int, request: Request
        ):
            """Voting power пользователя."""
            page, _user = await validate_page_request(slug, _PAGE_TYPE, request)
            init_data = request.headers.get("X-Init-Data", "")
            chat_id = (page.get("config") or {}).get("chat_id", "")
            if not chat_id:
                raise HTTPException(status_code=400, detail="chat_id not configured")
            headers = {"X-Init-Data": init_data} if init_data else {}
            return await proxy_get(
                f"{settings.democracy_url}/v1/delegations/{chat_id}/{user_id}/power",
                headers=headers,
            )
