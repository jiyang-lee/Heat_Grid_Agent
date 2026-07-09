/** API 소스 스위치. 기본(미설정)=mock. 실백엔드 연동 시 VITE_USE_MOCK=false. */
export const USE_MOCK = (import.meta.env.VITE_USE_MOCK ?? 'true') !== 'false'
