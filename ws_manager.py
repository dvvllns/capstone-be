from fastapi import WebSocket


class ConnectionManager:
    """사용자당 WebSocket 하나를 유지한다.

    방마다 연결을 열면 대화방을 옮길 때마다 TCP+TLS 핸드셰이크 비용이 들고,
    무선 모듈이 자주 깨어나 배터리 소모가 커진다. 연결은 하나만 두고 "지금 어느
    방을 보고 있는지"를 따로 기록해, 그 값으로 실시간 전달과 푸시를 가른다.
    """

    def __init__(self) -> None:
        self._connections: dict[int, WebSocket] = {}
        # user_id -> 현재 화면에 열어둔 room_id. None이면 채팅방 밖.
        self._active_rooms: dict[int, int | None] = {}

    async def connect(self, user_id: int, ws: WebSocket) -> None:
        await ws.accept()
        # 같은 계정으로 다시 접속하면 이전 연결은 정리한다.
        old = self._connections.get(user_id)
        if old is not None:
            try:
                await old.close()
            except Exception:
                pass
        self._connections[user_id] = ws
        self._active_rooms[user_id] = None

    def disconnect(self, user_id: int, ws: WebSocket | None = None) -> None:
        """[ws]를 주면 그 소켓이 아직 현재 연결일 때만 정리한다.

        재접속으로 소켓이 교체된 뒤 옛 소켓의 종료 처리가 늦게 도착해도
        새 연결을 끊지 않도록 한다.
        """
        current = self._connections.get(user_id)
        if current is None:
            return
        if ws is None or current is ws:
            self._connections.pop(user_id, None)
            self._active_rooms.pop(user_id, None)

    def enter_room(self, user_id: int, room_id: int) -> None:
        if user_id in self._connections:
            self._active_rooms[user_id] = room_id

    def leave_room(self, user_id: int) -> None:
        if user_id in self._connections:
            self._active_rooms[user_id] = None

    def get_active_room(self, user_id: int) -> int | None:
        return self._active_rooms.get(user_id)

    def is_viewing(self, user_id: int, room_id: int) -> bool:
        """그 사용자가 지금 이 채팅방 화면을 보고 있는지. 푸시 여부를 가른다."""
        return self._active_rooms.get(user_id) == room_id

    def is_connected(self, user_id: int) -> bool:
        return user_id in self._connections

    async def send_to_user(self, user_id: int, payload: dict) -> bool:
        """전송 성공 여부를 돌려준다. 실패하면 죽은 연결로 보고 정리한다."""
        ws = self._connections.get(user_id)
        if ws is None:
            return False
        try:
            await ws.send_json(payload)
            return True
        except Exception:
            self.disconnect(user_id, ws)
            return False


manager = ConnectionManager()
