from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.core.config import Settings, get_settings
from app.platform.database.session import get_db
from app.deepspace.workspace.workspace_service import WorkspaceFile, WorkspaceService
from app.deepspace.schemas.workspace import FileWriteRequest, ResolveFolderRequest, WorkspaceStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.post("/resolve-folder")
def resolve_folder(
    req: ResolveFolderRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, str]:
    """Resolves a folder name from the browser native directory picker to an absolute host path."""
    import os
    import re

    # Try to find user home for 'ravi' or fall back to system home
    user_home = "/home/ravi"
    if not os.path.exists(user_home):
        user_home = os.path.expanduser("~")

    folder_name = req.name.strip()
    current_path = req.current_path.strip()

    # Normalize slashes
    if current_path:
        current_path = re.sub(r"/{2,}", "/", current_path.replace("\\", "/"))

    # 1. Try directly under the current path
    if current_path:
        path1 = os.path.join(current_path, folder_name)
        if os.path.isdir(path1):
            return {"path": os.path.abspath(path1)}

    # 2. Try directly under user home
    path2 = os.path.join(user_home, folder_name)
    if os.path.isdir(path2):
        return {"path": os.path.abspath(path2)}

    # 3. Try under AverQel
    path3 = os.path.join(user_home, "AverQel", folder_name)
    if os.path.isdir(path3):
        return {"path": os.path.abspath(path3)}

    # 4. Search in user home subdirectories up to depth 2
    try:
        for root, dirs, _ in os.walk(user_home):
            # Limit depth
            depth = root[len(user_home):].count(os.sep)
            if depth > 2:
                dirs.clear() # don't descend deeper
                continue
            if folder_name in dirs:
                resolved = os.path.join(root, folder_name)
                return {"path": os.path.abspath(resolved)}
    except Exception:
        pass

    # 5. Fallback to current path or home
    fallback = os.path.join(current_path or user_home, folder_name)
    return {"path": os.path.abspath(fallback)}


@router.get("/root", response_model=dict[str, str])
async def get_workspace_root(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, str]:
    """Returns the absolute root directory path of the active workspace."""
    from app.deepspace.integrations.client_proxy import client_proxy_registry
    if client_proxy_registry.is_storage_connected(str(auth.tenant_id), str(auth.user_id)):
        return {"path": "AverQel://workspace"}
    service = WorkspaceService(tenant_id=str(auth.tenant_id), user_id=str(auth.user_id))
    return {"path": str(service.workspace_root.resolve())}


@router.get("/files", response_model=list[WorkspaceFile])
async def list_workspace_files(
    path: str = Query(".", description="Sub-path to list"),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[WorkspaceFile]:
    """Lists files in the user's sandboxed workspace."""
    service = WorkspaceService(tenant_id=str(auth.tenant_id), user_id=str(auth.user_id))
    return await service.list_dir_async(path)


@router.get("/file/content")
async def get_file_content(
    path: str = Query(..., description="Workspace-relative path to the file"),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, str]:
    """Reads the content of a file from the workspace."""
    service = WorkspaceService(tenant_id=str(auth.tenant_id), user_id=str(auth.user_id))
    try:
        content = await service.read_file_async(path)
        return {"content": content, "path": path}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"File not found: {path}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/file/download")
async def download_workspace_file(
    path: str = Query(..., description="Workspace-relative path to the file"),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> FileResponse:
    """Downloads a file from the workspace as a binary stream."""
    service = WorkspaceService(tenant_id=str(auth.tenant_id), user_id=str(auth.user_id))
    from app.deepspace.integrations.client_proxy import client_proxy_registry
    if client_proxy_registry.is_storage_connected(str(auth.tenant_id), str(auth.user_id)):
        try:
            content = await service.read_file_async(path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="File not found") from exc
        return Response(
            content=content.encode("utf-8"),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{os.path.basename(path)}"'},
        )
    host_path = service.get_full_host_path(path)
    if not os.path.exists(host_path) or os.path.isdir(host_path):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        filename = os.path.basename(host_path)
        return FileResponse(
            path=host_path,
            filename=filename,
            media_type="application/octet-stream",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/file", response_model=WorkspaceStatusResponse)
async def write_workspace_file(
    req: FileWriteRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> WorkspaceStatusResponse:
    """Writes or overwrites the content of a file in the workspace."""
    service = WorkspaceService(tenant_id=str(auth.tenant_id), user_id=str(auth.user_id))
    try:
        await service.write_file_async(req.path, req.content)
        return WorkspaceStatusResponse(
            status="success",
            message=f"File {req.path} written successfully.",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/file", response_model=WorkspaceStatusResponse)
async def create_workspace_file(
    path: str = Query(..., description="Workspace-relative path"),
    content: str | None = None,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> WorkspaceStatusResponse:
    """Creates a new file or directory in the workspace."""
    service = WorkspaceService(tenant_id=str(auth.tenant_id), user_id=str(auth.user_id))
    try:
        if path.endswith("/"):
            await service.create_directory_async(path)
            message = f"Directory {path} created."
        else:
            await service.write_file_async(path, content or "")
            message = f"File {path} created."
        return WorkspaceStatusResponse(status="success", message=message)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/file", response_model=WorkspaceStatusResponse)
async def delete_workspace_path(
    path: str = Query(..., description="Workspace-relative path"),
    recursive: bool = Query(False),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> WorkspaceStatusResponse:
    """Deletes a file or directory from the workspace."""
    service = WorkspaceService(tenant_id=str(auth.tenant_id), user_id=str(auth.user_id))
    try:
        await service.delete_path_async(path, recursive=recursive)
        return WorkspaceStatusResponse(
            status="success", message=f"Path {path} deleted."
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.patch("/file", response_model=WorkspaceStatusResponse)
async def rename_workspace_path(
    old_path: str = Query(..., description="Current relative path"),
    new_path: str = Query(..., description="New relative path"),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> WorkspaceStatusResponse:
    """Renames or moves a file/directory in the workspace."""
    service = WorkspaceService(tenant_id=str(auth.tenant_id), user_id=str(auth.user_id))
    try:
        final_path = await service.move_path_async(old_path, new_path)
        return WorkspaceStatusResponse(
            status="success", message=f"Moved to {final_path}"
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Source path not found.") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/copy", response_model=WorkspaceStatusResponse)
async def copy_workspace_path(
    source_path: str = Query(..., description="Source relative path"),
    destination_path: str = Query(..., description="Destination relative path"),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> WorkspaceStatusResponse:
    """Copies a file or directory in the workspace."""
    service = WorkspaceService(tenant_id=str(auth.tenant_id), user_id=str(auth.user_id))
    try:
        final_path = await service.copy_path_async(source_path, destination_path)
        return WorkspaceStatusResponse(
            status="success", message=f"Copied to {final_path}"
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Source path not found.") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.websocket("/terminal/ws")
async def terminal_websocket(
    websocket: WebSocket,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    """Provides a native, secure, interactive terminal websocket connected to the workspace docker shell container."""
    auth: AuthContext | None = None
    session = None
    on_chunk = None
    proxy_registered = False
    await websocket.accept()
    try:
        from app.deepspace.api.chats import _authenticate_websocket_auth_context
        auth = await _authenticate_websocket_auth_context(
            websocket, db=db, settings=settings
        )

        service = WorkspaceService(tenant_id=str(auth.tenant_id), user_id=str(auth.user_id))
        workspace_path = str(service.workspace_root)

        from app.deepspace.workspace.qsat_predictor import QSATPredictor
        qsat = QSATPredictor(workspace_path=workspace_path)

        session_id = websocket.query_params.get("session_id", "default")

        from app.deepspace.workspace.shell_manager import ShellManager
        session = ShellManager.get_session(
            tenant_id=str(auth.tenant_id),
            user_id=str(auth.user_id),
            workspace_path=workspace_path,
            session_id=session_id,
        )

        pid = session.process.pid if (session.process and hasattr(session.process, "pid")) else os.getpid()
        cmd_line = "/usr/bin/bash"
        if os.environ.get("AKS_DISABLE_SANDBOX") != "true":
            cmd_line = f"docker exec -it {session.container_name} bash --init-file /opt/averqel-ide/shellIntegration.sh"

        await websocket.send_json({
            "event": "connected",
            "data": {
                "session_id": session.id,
                "cwd": session.cwd,
                "pid": pid,
                "command_line": cmd_line,
                "session_name": "AverQel" if session_id == "averqel" else "bash",
                "active_venv": session.active_venv,
            }
        })

        async def on_chunk(chunk: dict[str, str]) -> None:
            try:
                await websocket.send_json({
                    "event": "output",
                    "data": {
                        "stream": chunk.get("stream", "stdout"),
                        "text": chunk.get("text", ""),
                    }
                })
            except Exception:
                pass
        session.listeners.add(on_chunk)
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                continue

            if data.get("event") == "rpc_response":
                from app.deepspace.integrations.client_proxy import client_proxy_registry
                client_proxy_registry.handle_response(data)
                continue

            if data.get("event") == "client_register":
                # Only an explicitly announced native client may become the
                # backend's local-PC execution proxy. Browser terminals also
                # use this websocket for server-side shell execution, but must
                # never receive agent RPC requests.
                if not proxy_registered:
                    from app.deepspace.integrations.client_proxy import client_proxy_registry

                    await client_proxy_registry.register_client(
                        tenant_id=str(auth.tenant_id),
                        user_id=str(auth.user_id),
                        websocket=websocket,
                        channel="workspace",
                    )
                    proxy_registered = True
                await websocket.send_json({
                    "event": "client_registered",
                    "data": {"ok": True, "mode": "local_pc"}
                })
                logger.info(
                    "Desktop client registered for local-PC shell execution: %s/%s",
                    auth.tenant_id,
                    auth.user_id,
                )
                continue

            action = data.get("action")
            if action == "execute":
                command = str(data.get("command", ""))
                qsat.record_command(command)

                async def run_command_task(cmd: str):
                    try:
                        await websocket.send_json({
                            "event": "status",
                            "data": {
                                "status": "running",
                                "command": cmd,
                            }
                        })
                        result = await session.stream_execute(
                            command=cmd,
                            on_chunk=on_chunk,
                        )
                        await websocket.send_json({
                            "event": "status",
                            "data": {
                                "status": "finished",
                                "exit_code": result.exit_code,
                                "cwd": session.cwd,
                                "active_venv": session.active_venv,
                            }
                        })
                    except Exception as e:
                        try:
                            await websocket.send_json({
                                "event": "output",
                                "data": {
                                    "stream": "stderr",
                                    "text": f"\nExecution error: {str(e)}\n",
                                }
                            })
                        except Exception:
                            pass

                asyncio.create_task(run_command_task(command))

            elif action == "typing":
                input_val = str(data.get("input", "")).strip()
                cwd_val = str(data.get("cwd", session.cwd))
                prediction_result = qsat.predict_next_command(input_val, cwd_val)
                phase_state = qsat.get_phase_state(cwd_val)
                await websocket.send_json({
                    "event": "prediction",
                    "data": {
                        "prediction": prediction_result.get("prediction", ""),
                        "probability": prediction_result.get("probability", 0.0),
                        "phase_state": phase_state
                    }
                })

            elif action == "kill":
                session.kill()
                await websocket.send_json({
                    "event": "status",
                    "data": {
                        "status": "killed",
                    }
                })

            elif action == "cd":
                new_path = str(data.get("path", "")).strip()
                if new_path:
                    try:
                        resolved_path = service._resolve_path(new_path)
                        if resolved_path.exists() and resolved_path.is_dir():
                            session.cwd = str(resolved_path)
                            await websocket.send_json({
                                "event": "connected",
                                "data": {
                                    "session_id": session.id,
                                    "cwd": session.cwd,
                                }
                            })
                    except Exception as e:
                        try:
                            await websocket.send_json({
                                "event": "output",
                                "data": {
                                    "stream": "stderr",
                                    "text": f"\nDirectory change error: {str(e)}\n",
                                }
                            })
                        except Exception:
                            pass

    except WebSocketDisconnect:
        if auth is not None:
            from app.deepspace.integrations.client_proxy import client_proxy_registry

            if proxy_registered:
                client_proxy_registry.unregister_client(
                    str(auth.tenant_id), str(auth.user_id), channel="workspace", websocket=websocket
                )
            if session is not None and on_chunk is not None:
                session.listeners.discard(on_chunk)
    except Exception:
        if auth is not None:
            from app.deepspace.integrations.client_proxy import client_proxy_registry

            if proxy_registered:
                client_proxy_registry.unregister_client(
                    str(auth.tenant_id), str(auth.user_id), channel="workspace", websocket=websocket
                )
            if session is not None and on_chunk is not None:
                session.listeners.discard(on_chunk)
        logger.exception("Terminal websocket connection error")
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
