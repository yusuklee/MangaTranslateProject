//백엔드 주소. 개발(vite dev)에서는 8000 번 백엔드, 데스크톱 앱에서는 프런트를 백엔드가 직접 서빙하니 같은 주소
export const API = import.meta.env.DEV ? "http://localhost:8000" : window.location.origin;
export const FONT_URL = `${API}/fontfiles/`;
