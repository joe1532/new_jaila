-- question_number i JSONL er text (fx '1', 'IC', 'II'), ikke integer.

SET search_path TO skat, public;

ALTER TABLE skat.chunks
    ALTER COLUMN question_number TYPE text;
