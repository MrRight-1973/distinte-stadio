-- Archivio della Distinta Digitale su Supabase.
-- Da eseguire una sola volta: Supabase > SQL Editor > New query > incolla tutto > Run.

-- Partite: una riga per partita, con tutta la cronaca (note, foto, resoconto) nel campo "dati".
create table if not exists public.partite (
  id          text primary key,
  casa        text,
  ospite      text,
  campionato  text,
  data        text,
  gol_casa    integer,
  gol_ospite  integer,
  corrente    boolean not null default false,  -- la partita aperta nell'app
  dati        jsonb not null,
  creato      timestamptz not null default now(),
  aggiornato  timestamptz not null default now()
);
create index if not exists partite_aggiornato on public.partite (aggiornato desc);

-- Nessun accesso pubblico: senza regole (policy) solo la chiave segreta dell'app può leggere e scrivere.
alter table public.partite enable row level security;

-- Spazio file privato per foto (referto, distinte, partita) e note vocali.
insert into storage.buckets (id, name, public)
values ('archivio', 'archivio', false)
on conflict (id) do nothing;
