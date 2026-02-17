from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from psycopg2.extras import RealDictCursor

from app.auth import verify_password
from web.deps import get_db

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": None,
    })


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    conn=Depends(get_db),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, username, password_hash, full_name, role_code, is_active
            FROM app_users WHERE username = %s
            """,
            (username,),
        )
        user = cur.fetchone()

    if not user or not user["is_active"]:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Неверный логин или пароль",
        })

    if not verify_password(password, user["password_hash"]):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Неверный логин или пароль",
        })

    # Сохраняем в сессию
    request.session["user"] = {
        "id": user["id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "role_code": user["role_code"],
    }

    return RedirectResponse("/schedule", status_code=302)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)
