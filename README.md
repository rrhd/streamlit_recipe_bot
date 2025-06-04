# Streamlit Recipe Bot

This app provides advanced and simple search tools for finding recipes and a cookbook library interface.

## Reset Fields Feature

The Advanced Search page now includes a **Reset Fields** button to quickly restore all search inputs to their default values.

## Supabase Setup

Scripts in the `scripts/` directory help initialize and migrate the profile database to Supabase.

1. Create a project and write credentials. Add `supabase_access_token` to
   `.streamlit/secrets.toml` and run:

   ```bash
   python scripts/init_supabase_project.py
   ```

2. Upload existing profiles to the new instance:

   ```bash
   PYTHONPATH=. python scripts/setup_supabase.py
   ```

3. Verify the connection:

   ```bash
   PYTHONPATH=. python scripts/check_supabase.py
   ```

The scripts read Supabase credentials from `.streamlit/secrets.toml`. If that
file is missing you can instead supply `SUPABASE_ACCESS_TOKEN`,
`SUPABASE_URL`, `SUPABASE_API_KEY`, and `SUPABASE_DB_URL` as environment
variables.
