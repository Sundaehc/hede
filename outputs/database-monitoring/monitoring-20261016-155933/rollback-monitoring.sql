ALTER SYSTEM RESET log_min_duration_statement;
ALTER SYSTEM RESET log_temp_files;
ALTER SYSTEM RESET log_statement;
ALTER SYSTEM RESET log_parameter_max_length;
ALTER SYSTEM RESET log_line_prefix;
ALTER SYSTEM RESET shared_preload_libraries;
ALTER SYSTEM RESET pg_stat_statements.track_planning;
SELECT pg_reload_conf();
