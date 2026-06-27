-- 000_extensions.sql
-- 목적: 운영 입력 스키마가 의존하는 PostgreSQL 확장 설치
-- 근거: sensor_readings는 고빈도 시계열이라 TimescaleDB hypertable로 운영한다 (AGENTS.md DB 규칙)
--
-- 실행 순서: 000 -> 001 -> 002 -> 003 -> 004

CREATE EXTENSION IF NOT EXISTS timescaledb;
