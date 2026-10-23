-- Contatore anonimo delle visite alla pagina spettatori (distinta-live).
-- Da eseguire una sola volta: Supabase > SQL Editor > New query > incolla tutto > Run.
--
-- Una riga per ogni apertura della pagina: quale partita mostrava, il giorno e un numero a caso che il
-- telefono si tiene (per contare i dispositivi diversi). Niente nomi, niente indirizzi IP.

create table if not exists public.visite (
  id           bigserial primary key,
  creato       timestamptz not null default now(),
  giorno       date not null default (now() at time zone 'Europe/Rome')::date,
  partita      text not null check (char_length(partita) <= 200),
  dispositivo  text not null check (char_length(dispositivo) <= 64)
);
create index if not exists visite_partita on public.visite (partita);

-- Nessuno legge o scrive la tabella direttamente: la pagina pubblica può solo aggiungere una visita
-- con la funzione qui sotto, l'app (chiave segreta) legge solo il riepilogo.
alter table public.visite enable row level security;

create or replace function public.conta_visita(p_partita text, p_dispositivo text)
returns void
language sql
security definer
set search_path = public
as $$
  insert into public.visite (partita, dispositivo)
  values (left(coalesce(nullif(trim(p_partita), ''), 'Pagina'), 200),
          left(coalesce(nullif(trim(p_dispositivo), ''), 'sconosciuto'), 64));
$$;
revoke all on function public.conta_visita(text, text) from public;
grant execute on function public.conta_visita(text, text) to anon, authenticated, service_role;

create or replace function public.riepilogo_visite()
returns table (partita text, primo_giorno date, ultimo_giorno date, aperture bigint, dispositivi bigint)
language sql
security definer
set search_path = public
as $$
  select partita, min(giorno), max(giorno), count(*), count(distinct dispositivo)
  from public.visite
  group by partita
  order by max(creato) desc;
$$;
revoke all on function public.riepilogo_visite() from public, anon, authenticated;
grant execute on function public.riepilogo_visite() to service_role;
