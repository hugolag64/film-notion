import { useEffect, useState } from 'react';

/** Debounced TMDB film search with one action button per result. */
export default function TMDBSearchBox({ isDarkMode, search, placeholder, actionLabel, onPick }) {
    const [query, setQuery] = useState('');
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        const text = query.trim();
        if (text.length < 2) {
            setResults([]);
            setError(null);
            return undefined;
        }
        let cancelled = false;
        const timer = setTimeout(async () => {
            setLoading(true);
            try {
                const found = await search(text);
                if (!cancelled) {
                    setResults((found || []).slice(0, 8));
                    setError(null);
                }
            } catch {
                if (!cancelled) setError('Recherche TMDB indisponible, réessaie plus tard.');
            } finally {
                if (!cancelled) setLoading(false);
            }
        }, 300);
        return () => { cancelled = true; clearTimeout(timer); };
    }, [query, search]);

    const pick = (result) => {
        setQuery('');
        setResults([]);
        onPick(result);
    };

    const muted = isDarkMode ? 'text-white/60' : 'text-[#425466]';
    return <div>
        <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={placeholder}
            aria-label={placeholder}
            className={`w-full rounded-xl border px-4 py-2.5 text-sm outline-none focus:border-[#635bff] ${isDarkMode ? 'border-white/15 bg-black text-white placeholder:text-white/40' : 'border-[#e3e8ee] bg-white text-[#0a2540]'}`}
        />
        {loading && <p className={`mt-2 text-xs ${muted}`}>Recherche…</p>}
        {error && <p role="alert" className="mt-2 text-xs text-rose-500">{error}</p>}
        {results.length > 0 && <ul className={`mt-2 overflow-hidden rounded-xl border ${isDarkMode ? 'border-white/10 bg-[#0a0a0a]' : 'border-[#e3e8ee] bg-white'}`}>
            {results.map((result) => <li key={result.tmdb_id} className="flex items-center gap-3 px-3 py-2">
                {result.poster_url
                    ? <img src={result.poster_url} alt="" className="h-12 w-8 shrink-0 rounded object-cover" loading="lazy" />
                    : <div className="h-12 w-8 shrink-0 rounded bg-black/10 dark:bg-white/10" />}
                <span className={`min-w-0 flex-1 truncate text-sm ${isDarkMode ? 'text-white' : 'text-[#0a2540]'}`}>
                    {result.title} <span className={muted}>{result.release_date ? result.release_date.slice(0, 4) : ''}</span>
                </span>
                <button type="button" onClick={() => pick(result)} className="shrink-0 rounded-lg bg-[#635bff] px-3 py-1.5 text-xs font-semibold text-white">{actionLabel}</button>
            </li>)}
        </ul>}
    </div>;
}
