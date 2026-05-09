import { useState } from "react";

const phases = [
  {
    id: "P1",
    title: "Data collection & ingestion",
    days: "3–4 days",
    color: "#C84B31",
    status: "foundation",
    objective: "Build the raw data layer — scrape, fetch, download, and store all source data into a normalised SQLite database.",
    tasks: [
      {
        name: "Scrape rental listings",
        detail: "Write a Python scraper (BeautifulSoup + requests) for Domain.com.au or Flatmates.com.au. Collect: suburb, price, bedrooms, coordinates, listing URL, and the full description text. Target 2,000+ listings across Greater Melbourne. Handle pagination, rate limiting, and duplicate detection.",
        output: "raw/listings.json",
      },
      {
        name: "Fetch PTV transit data",
        detail: "Download train performance data from data.vic.gov.au — on-time percentage, average delay in minutes, per line per station per month. Use the PTV API or bulk CSV downloads. Parse timetable data to compute actual vs scheduled arrival deltas.",
        output: "raw/ptv_performance.csv",
      },
      {
        name: "Query OSM amenities",
        detail: "Use the Overpass API to count amenities within each suburb boundary — supermarkets, cafes, parks, gyms, pharmacies, schools. Query by bounding box using suburb geometries. Store counts and coordinates.",
        output: "raw/amenities.json",
      },
      {
        name: "Download ABS data",
        detail: "Get Census 2021 median household income by SA2 area from abs.gov.au. Download ASGS suburb boundary shapefiles (.shp). Map SA2 areas to suburbs using the ABS correspondence files.",
        output: "raw/income.csv + raw/boundaries.shp",
      },
      {
        name: "Design SQLite schema",
        detail: "Create 5 normalised tables: listings (id, suburb_id, price, bedrooms, lat, lng, description, url, scraped_at), suburbs (id, name, geometry, sa2_code), transit_performance (suburb_id, line, on_time_pct, avg_delay), amenities (suburb_id, type, count), income (suburb_id, median_household_income). Add foreign keys and indexes.",
        output: "data/melbourne.db + scripts/05_create_db_schema.sql",
      },
      {
        name: "Create SQL views",
        detail: "Write 3–4 SQL views that pre-join common queries: suburb_summary (median rent + income + transit + amenity count), listing_detail (listing + suburb + income), transit_by_line (avg delay ranked). These views feed both Tableau and the RAG pipeline later.",
        output: "scripts/06_create_views.sql",
      },
    ],
    skills: ["Web scraping", "API ingestion", "SQL schema design", "Data cleaning"],
    tools: ["Python", "BeautifulSoup", "requests", "SQLite", "Pandas"],
    deliverables: ["Scraping scripts", "Populated SQLite DB", "Schema diagram in README"],
    dependencies: "None — this is the foundation",
    risk: "Domain.com.au may block scraping. Fallback: use Flatmates.com.au or the Domain API (free tier, 500 calls/day). Can also supplement with static Kaggle Melbourne housing datasets.",
  },
  {
    id: "P2",
    title: "NLP on listing descriptions",
    days: "2–3 days",
    color: "#1D9E75",
    status: "analysis",
    objective: "Extract structured insights from unstructured listing text — identify marketing language, euphemisms, and compute a per-suburb honesty score.",
    tasks: [
      {
        name: "Keyword & entity extraction",
        detail: "Run spaCy NER on all listing descriptions. Extract: location claims ('5 min walk to station'), amenity mentions ('near shops'), transport references ('close to tram'). Count superlative adjectives per listing ('stunning', 'gorgeous', 'spacious'). Store as structured features.",
        output: "nlp_features table in SQLite",
      },
      {
        name: "Sentiment analysis",
        detail: "Score each listing's positivity using VADER or TextBlob. Compute a 'superlative density' metric (marketing adjectives per 100 words). Flag outlier listings with unusually high promotional language.",
        output: "sentiment_score + superlative_density columns",
      },
      {
        name: "LLM euphemism detection",
        detail: "Use Ollama (Llama 3.1 8B locally) to classify euphemistic language. Prompt: given a listing description, extract structured JSON — {claimed_walk_time, renovation_state, size_indicator, noise_level, red_flags}. Batch-process all listings with a 2-second delay. This catches what VADER can't: 'cosy' = tiny, 'character home' = needs work.",
        output: "llm_features table in SQLite",
      },
      {
        name: "Buzzword inflation index",
        detail: "Compare marketing language frequency against actual suburb data. For each suburb: if listings say 'vibrant nightlife' but the OSM cafe/bar count is below median, that's inflation. Compute correlation between claimed and actual amenity presence. Output a per-suburb buzzword_inflation_score (0–1, higher = more inflated).",
        output: "buzzword_inflation_score in suburb_summary view",
      },
      {
        name: "Listing honesty score",
        detail: "Combine sentiment analysis, euphemism detection, and buzzword inflation into a composite 'listing honesty score' per suburb. Suburbs where listings accurately reflect reality score high; suburbs with heavy marketing spin score low. Store back into SQLite.",
        output: "honesty_score in suburb_summary view",
      },
    ],
    skills: ["NLP / text analysis", "LLM prompt engineering", "Feature engineering", "SQL"],
    tools: ["spaCy", "VADER / TextBlob", "Ollama + Llama 3.1", "LangChain", "Pandas"],
    deliverables: ["NLP analysis notebook", "Buzzword analysis charts", "Honesty scores in DB"],
    dependencies: "P1 — SQLite DB must be populated with listings",
    risk: "Ollama needs ~5GB RAM for Llama 3.1 8B. If laptop can't handle it, use Groq free tier or Google Gemini free tier as fallback.",
  },
  {
    id: "P3",
    title: "Geospatial analysis & liveability scoring",
    days: "2–3 days",
    color: "#534AB7",
    status: "analysis",
    objective: "Compute a composite liveability score per suburb using geospatial methods, and identify hidden gems vs overpriced traps.",
    tasks: [
      {
        name: "Spatial joins",
        detail: "Load ABS suburb boundary shapefiles into GeoPandas. Spatially join all suburb-level metrics (rent, income, transit, amenities, NLP scores) onto the geometry. Verify all 300+ suburbs have complete data; flag and handle missing values.",
        output: "GeoDataFrame with all metrics per suburb",
      },
      {
        name: "Derived metrics",
        detail: "Compute rent-to-income ratio per suburb. Calculate transit reliability percentile (weighted by proximity to train stations + on-time %). Build walkability index from OSM amenity density (count per sq km). Percentile-rank all metrics across Melbourne for fair comparison.",
        output: "Derived columns in suburb GeoDataFrame",
      },
      {
        name: "Composite liveability score",
        detail: "Design a weighted scoring formula: rent affordability (30%) + transit reliability (25%) + walkability (20%) + listing honesty (15%) + amenity variety (10%). Document the methodology and rationale for each weight. Normalise to 0–10 scale.",
        output: "liveability_score column + methodology.md",
      },
      {
        name: "Choropleth maps",
        detail: "Generate 3 Folium choropleth maps: (1) median rent by suburb, (2) liveability score by suburb, (3) 'value gap' — liveability rank minus rent rank. Positive gap = hidden gem, negative = overpriced. Add hover tooltips with key metrics.",
        output: "3 interactive HTML maps",
      },
      {
        name: "Hidden gems & overpriced traps",
        detail: "Identify top 5 suburbs with highest positive value gap (high liveability, below-average rent) and top 5 with highest negative gap. Generate a summary table with key reasons for each classification.",
        output: "Top 5 gems + top 5 traps analysis",
      },
      {
        name: "LLM suburb summaries",
        detail: "Use Ollama to generate a 2–3 sentence natural language summary per suburb from its data row. Template: '{suburb} scores {score}/10. {strength_1} and {strength_2}, but {weakness}. Listings here tend to {buzzword_pattern}.' Batch-generate for all suburbs. Store in SQLite for use in Tableau tooltips and Streamlit.",
        output: "suburb_summaries table in SQLite",
      },
    ],
    skills: ["Geospatial analysis", "Composite scoring", "LLM data-to-narrative", "Business storytelling"],
    tools: ["GeoPandas", "Folium", "Shapely", "Ollama", "SQL"],
    deliverables: ["Scored suburb table", "3 choropleth maps", "Methodology doc", "Auto-generated suburb summaries"],
    dependencies: "P1 + P2 — needs all data + NLP scores in the database",
    risk: "Some suburbs may have too few listings for statistically meaningful scores. Set a minimum threshold (e.g., 10+ listings) and mark others as 'insufficient data'.",
  },
  {
    id: "P4",
    title: "Tableau dashboard",
    days: "2–3 days",
    color: "#185FA5",
    status: "output",
    objective: "Build a polished, 3-tab executive dashboard on Tableau Public that a non-technical stakeholder can use independently.",
    tasks: [
      {
        name: "Export clean CSVs",
        detail: "Export suburb_summary SQL view as a flat CSV with all metrics per suburb. Export a separate listings-level CSV for the deep-dive tab. Include the LLM-generated suburb summaries as a text column. Ensure data types and formatting are Tableau-ready.",
        output: "data/processed/suburb_summary.csv + listings.csv",
      },
      {
        name: "Tab 1 — Overview map",
        detail: "Choropleth of Melbourne suburbs coloured by liveability score (diverging palette: red = low, green = high). Filters: budget slider, bedroom count, minimum liveability score. Tooltip: suburb name, median rent, rent-to-income ratio, transit score, the LLM-generated summary. Map should zoom to Greater Melbourne with proper projection.",
        output: "Tableau worksheet: Overview",
      },
      {
        name: "Tab 2 — Suburb deep-dive",
        detail: "Select-a-suburb interaction: clicking a suburb on the map or from a dropdown opens a breakdown panel. Show: rent distribution histogram, transit delay bar chart by line, top 5 buzzwords used in that suburb's listings, amenity type breakdown (bar), honesty score gauge. Use the LLM summary as the header text.",
        output: "Tableau worksheet: Deep-dive",
      },
      {
        name: "Tab 3 — Value scatter",
        detail: "Scatter plot: median rent (x-axis) vs liveability score (y-axis). Point size = listing volume. Colour = value gap classification (gem/fair/overpriced). Quadrant labels. Clickable points linking to Tab 2. Reference lines at median rent and median liveability.",
        output: "Tableau worksheet: Value analysis",
      },
      {
        name: "Polish & publish",
        detail: "Consistent colour palette across all tabs. Proper axis labels, number formatting ($xxx/wk), meaningful tooltips. Title card explaining methodology. Mobile-responsive layout. Publish to Tableau Public — get shareable URL.",
        output: "Published Tableau Public dashboard",
      },
    ],
    skills: ["Dashboard design", "Data visualisation", "Stakeholder communication"],
    tools: ["Tableau Public", "CSV exports from SQL"],
    deliverables: ["Published Tableau dashboard with public URL", "Screenshots for README"],
    dependencies: "P3 — needs the scored suburb table and LLM summaries",
    risk: "Tableau Public has a 10M row limit and 10GB workbook limit — well within our data size. Suburb boundaries may need simplification for Tableau's map layer; use simplified geometries.",
  },
  {
    id: "P5",
    title: "Streamlit app + RAG conversational advisor",
    days: "4–5 days",
    color: "#0F6E56",
    status: "output",
    highlight: true,
    objective: "Build and deploy a Streamlit app with a RAG-powered conversational suburb advisor — users ask natural language questions and get data-backed, personalised answers.",
    tasks: [
      {
        name: "App structure & navigation",
        detail: "Set up multi-page Streamlit app with 4 pages: Suburb Finder (filters + ranking), Compare (side-by-side), Buzzword Decoder (paste a listing), and the AI Advisor (RAG chat). Use st.navigation for clean page routing. Copy the SQLite DB into the app directory.",
        output: "streamlit_app/app.py + pages/",
      },
      {
        name: "Suburb finder page",
        detail: "User inputs max weekly rent, preferred bedrooms, and drags sliders to weight priorities (transit vs walkability vs affordability). App queries SQLite, re-ranks suburbs in real time using the weighted scoring formula, and displays top 10 with Plotly choropleth highlighting those suburbs on a map.",
        output: "pages/01_suburb_finder.py",
      },
      {
        name: "Comparison page",
        detail: "Select 2–3 suburbs from dropdowns. Show radar charts (Plotly) comparing all liveability dimensions side-by-side. Display the LLM-generated summary for each. Plotly map highlighting both areas with colour coding.",
        output: "pages/02_compare.py",
      },
      {
        name: "Buzzword decoder page",
        detail: "Text input: paste any rental listing description. App runs the NLP pipeline (spaCy + Ollama) live — returns a honesty score, flagged red-flag phrases with explanations, and what the data actually shows for that suburb. Visual output with highlighted text spans.",
        output: "pages/03_buzzword_decoder.py",
      },
      {
        name: "RAG pipeline — query parser",
        detail: "Build an intent + filter extraction layer. User message goes to the LLM with a system prompt: 'Extract structured filters from this rental question. Output JSON: {max_rent, min_bedrooms, needs_train, lifestyle_priority, specific_suburbs_mentioned}'. This converts natural language to SQL-ready parameters.",
        output: "rag/query_parser.py",
      },
      {
        name: "RAG pipeline — SQL retriever",
        detail: "Take the parsed filters and build a parameterised SQL query against the suburb_summary view. Retrieve top 5–10 matching suburbs with all their metrics, LLM summaries, and top listing buzzwords. Format results as a structured context block.",
        output: "rag/retriever.py",
      },
      {
        name: "RAG pipeline — context builder & prompt",
        detail: "Assemble the final LLM prompt: system message (role: Melbourne rental advisor, tone: helpful and specific, constraints: only use provided data, cite numbers) + retrieved suburb data as context + conversation history + user's latest question. Use LangChain's ChatPromptTemplate for clean templating.",
        output: "rag/prompt_templates.py",
      },
      {
        name: "RAG pipeline — LLM response generation",
        detail: "Send the assembled prompt to the LLM (Ollama locally / Groq in production). Stream the response token-by-token into the Streamlit chat UI using st.write_stream. Maintain conversation history in st.session_state for multi-turn follow-ups.",
        output: "rag/chain.py",
      },
      {
        name: "RAG pipeline — provider abstraction",
        detail: "Build a config layer that swaps LLM providers via environment variable: OLLAMA for local dev, GROQ for deployed app (free tier), with optional GEMINI/OPENAI fallbacks. Single get_llm() function used everywhere. This ensures the deployed Streamlit app works without a local GPU.",
        output: "rag/config.py",
      },
      {
        name: "AI advisor chat page",
        detail: "Streamlit chat interface using st.chat_message and st.chat_input. Shows a welcome message with example questions. Maintains conversation history. Displays retrieved suburb data in expandable cards alongside the chat response. Add a 'Sources' expander showing which SQL query was run and which suburbs were retrieved — transparency builds trust.",
        output: "pages/04_ai_advisor.py",
      },
      {
        name: "Deploy to Streamlit Cloud",
        detail: "Add requirements.txt with all dependencies. Set GROQ_API_KEY as a Streamlit Cloud secret. Configure the app to use Groq in production and Ollama in local dev. Test the deployed app end-to-end. Get the public URL.",
        output: "Live app on Streamlit Community Cloud",
      },
    ],
    skills: ["RAG architecture", "LLM integration", "Prompt engineering", "App development", "Deployment"],
    tools: ["Streamlit", "LangChain", "Ollama / Groq", "Plotly", "SQLite", "spaCy"],
    deliverables: ["Live Streamlit app with RAG chat", "Deployable on Streamlit Cloud"],
    dependencies: "P2 (NLP pipeline) + P3 (scoring + summaries). Can be built in parallel with P4.",
    risk: "Groq free tier has rate limits (30 RPM). Add graceful error handling and a 'please wait' message if rate-limited. Cache frequent queries in st.session_state to reduce API calls.",
  },
  {
    id: "P6",
    title: "Documentation & storytelling",
    days: "1–2 days",
    color: "#5F5E5A",
    status: "polish",
    objective: "Package everything into a portfolio-ready GitHub repo with compelling documentation, a findings blog post, and a video walkthrough.",
    tasks: [
      {
        name: "GitHub README",
        detail: "Write a polished README with: project overview, architecture diagram, data sources with links, methodology explanation, screenshots of Tableau and Streamlit, links to both live artefacts, tech stack badges, setup instructions for running locally, and a 'Key Findings' section with the top insights.",
        output: "README.md",
      },
      {
        name: "Findings blog post",
        detail: "Write a 600–800 word blog-style piece: 'The 5 Most Overpriced Suburbs in Melbourne (and the Hidden Gems the Data Says You're Ignoring)'. Include 2–3 charts. This is what you share on LinkedIn and in job applications. Focus on the 'so what' — make it interesting to a non-technical reader.",
        output: "docs/blog_post.md",
      },
      {
        name: "Loom walkthrough",
        detail: "Record a 3–4 minute video: (1) state the problem (30s), (2) show the Tableau dashboard — filter, drill down, scatter plot (60s), (3) demo the Streamlit app — use the suburb finder, decode a listing, then ask the AI advisor a question and show the response (90s), (4) summarise key findings (30s).",
        output: "Loom link embedded in README",
      },
      {
        name: "Repo cleanup",
        detail: "Ensure all notebooks run top-to-bottom without errors. Add .gitignore (exclude .db files, __pycache__, .env). Clean commit history with meaningful messages. Add a LICENSE (MIT). Verify the Streamlit app requirements.txt is complete. Add a SETUP.md with local installation instructions.",
        output: "Clean, professional GitHub repo",
      },
    ],
    skills: ["Business storytelling", "Technical documentation", "Portfolio presentation"],
    tools: ["Markdown", "Loom", "Git"],
    deliverables: ["Polished README", "Blog post", "Loom video", "Clean repo"],
    dependencies: "P4 + P5 — both outputs must be live",
    risk: "None — this is the packaging layer. Timebox to 2 days max; don't over-polish at the expense of not shipping.",
  },
];

const statusColors = {
  foundation: { bg: "#FAECE7", text: "#993C1D", label: "Foundation" },
  analysis: { bg: "#EEEDFE", text: "#3C3489", label: "Analysis" },
  output: { bg: "#E6F1FB", text: "#0C447C", label: "Output" },
  polish: { bg: "#F1EFE8", text: "#5F5E5A", label: "Polish" },
};

function PhaseCard({ phase, isOpen, onToggle }) {
  const sc = statusColors[phase.status];
  return (
    <div
      style={{
        borderLeft: `3px solid ${phase.color}`,
        background: isOpen ? "rgba(255,255,255,0.85)" : "rgba(255,255,255,0.55)",
        backdropFilter: "blur(8px)",
        borderRadius: "0 8px 8px 0",
        marginBottom: 8,
        transition: "all 0.2s ease",
        boxShadow: isOpen ? "0 4px 20px rgba(0,0,0,0.08)" : "none",
      }}
    >
      <div
        onClick={onToggle}
        style={{
          padding: "16px 20px",
          cursor: "pointer",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12, flex: 1 }}>
          <span
            style={{
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: 13,
              fontWeight: 600,
              color: phase.color,
              minWidth: 28,
            }}
          >
            {phase.id}
          </span>
          <div>
            <h3 style={{ fontSize: 15, fontWeight: 600, color: "#1a1a1a", margin: 0, lineHeight: 1.3, fontFamily: "'Instrument Sans', sans-serif" }}>
              {phase.title}
              {phase.highlight && (
                <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: 0.5, textTransform: "uppercase", marginLeft: 8, padding: "2px 8px", borderRadius: 4, background: "#E1F5EE", color: "#0F6E56" }}>
                  RAG pipeline
                </span>
              )}
            </h3>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: 0.5, textTransform: "uppercase", padding: "2px 8px", borderRadius: 4, background: sc.bg, color: sc.text }}>{sc.label}</span>
          <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12, color: "#888" }}>{phase.days}</span>
          <span style={{ fontSize: 12, color: "#aaa", transition: "transform 0.2s", transform: isOpen ? "rotate(180deg)" : "rotate(0)" }}>▼</span>
        </div>
      </div>

      {isOpen && (
        <div style={{ padding: "0 20px 20px 60px", fontSize: 13, lineHeight: 1.65, color: "#444" }}>
          <p style={{ fontStyle: "italic", color: "#666", margin: "0 0 16px", paddingBottom: 12, borderBottom: "1px solid #eee" }}>
            {phase.objective}
          </p>

          <div style={{ marginBottom: 16 }}>
            <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", color: "#999", margin: "0 0 8px" }}>Tasks</p>
            {phase.tasks.map((task, i) => (
              <div key={i} style={{ marginBottom: 12, paddingLeft: 14, borderLeft: `2px solid ${phase.color}22` }}>
                <p style={{ fontWeight: 600, color: "#1a1a1a", margin: "0 0 3px", fontSize: 13 }}>{task.name}</p>
                <p style={{ margin: "0 0 3px", color: "#555", fontSize: 12 }}>{task.detail}</p>
                <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: "#888", background: "#f5f5f0", padding: "1px 6px", borderRadius: 3 }}>
                  → {task.output}
                </span>
              </div>
            ))}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            <div>
              <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", color: "#999", margin: "0 0 6px" }}>Skills proven</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                {phase.skills.map((s, i) => (
                  <span key={i} style={{ fontSize: 11, padding: "2px 7px", borderRadius: 4, background: "#E1F5EE", color: "#0F6E56", fontWeight: 500 }}>{s}</span>
                ))}
              </div>
            </div>
            <div>
              <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", color: "#999", margin: "0 0 6px" }}>Tools used</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                {phase.tools.map((t, i) => (
                  <span key={i} style={{ fontSize: 11, padding: "2px 7px", borderRadius: 4, background: "#f0efec", color: "#333", fontWeight: 500, border: "1px solid #e0dfdc" }}>{t}</span>
                ))}
              </div>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", color: "#999", margin: "0 0 6px" }}>Deliverables</p>
              {phase.deliverables.map((d, i) => (
                <p key={i} style={{ margin: "0 0 2px", fontSize: 12, color: "#333" }}>✓ {d}</p>
              ))}
            </div>
            <div>
              <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", color: "#999", margin: "0 0 6px" }}>Dependencies</p>
              <p style={{ margin: "0 0 8px", fontSize: 12, color: "#555" }}>{phase.dependencies}</p>
              <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", color: "#999", margin: "0 0 6px" }}>Risk & mitigation</p>
              <p style={{ margin: 0, fontSize: 12, color: "#555" }}>{phase.risk}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [openPhases, setOpenPhases] = useState(new Set(["P5"]));
  const toggle = (id) => {
    setOpenPhases((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const totalMin = 15;
  const totalMax = 20;

  return (
    <div style={{ fontFamily: "'Instrument Sans', -apple-system, sans-serif", minHeight: "100vh", background: "#f7f6f3", padding: "32px 16px" }}>
      <link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet" />

      <div style={{ maxWidth: 800, margin: "0 auto" }}>
        {/* Header */}
        <div style={{ marginBottom: 32 }}>
          <p style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, fontWeight: 600, letterSpacing: 1.5, textTransform: "uppercase", color: "#C84B31", margin: "0 0 8px" }}>
            Strategic project roadmap
          </p>
          <h1 style={{ fontSize: 28, fontWeight: 700, color: "#1a1a1a", margin: "0 0 8px", lineHeight: 1.25 }}>
            Melbourne rental & liveability intelligence platform
          </h1>
          <p style={{ fontSize: 14, color: "#666", margin: "0 0 20px", lineHeight: 1.6, maxWidth: 620 }}>
            End-to-end data analytics project with RAG-powered conversational AI. Covers scraping, SQL, NLP, geospatial analysis, Tableau dashboarding, and a deployed Streamlit app with an intelligent suburb advisor.
          </p>

          {/* Summary stats */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
            {[
              { label: "Phases", value: "6" },
              { label: "Timeline", value: `${totalMin}–${totalMax} days` },
              { label: "Data sources", value: "5" },
              { label: "Portfolio artefacts", value: "5" },
            ].map((s, i) => (
              <div key={i} style={{ background: "#eeeee8", borderRadius: 8, padding: "10px 14px", textAlign: "center" }}>
                <p style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 18, fontWeight: 600, color: "#1a1a1a", margin: 0 }}>{s.value}</p>
                <p style={{ fontSize: 11, color: "#888", margin: "2px 0 0", textTransform: "uppercase", letterSpacing: 0.5, fontWeight: 500 }}>{s.label}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Dependency map */}
        <div style={{ background: "rgba(255,255,255,0.6)", borderRadius: 8, padding: "14px 18px", marginBottom: 20, border: "1px solid #e8e7e4" }}>
          <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", color: "#999", margin: "0 0 8px" }}>Critical path & dependencies</p>
          <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12, color: "#555", lineHeight: 2 }}>
            <span style={{ color: "#C84B31", fontWeight: 600 }}>P1</span>
            <span style={{ color: "#bbb" }}> ──→ </span>
            <span style={{ color: "#1D9E75", fontWeight: 600 }}>P2</span>
            <span style={{ color: "#bbb" }}> ──→ </span>
            <span style={{ color: "#534AB7", fontWeight: 600 }}>P3</span>
            <span style={{ color: "#bbb" }}> ──┬──→ </span>
            <span style={{ color: "#185FA5", fontWeight: 600 }}>P4</span>
            <span style={{ color: "#888" }}> (Tableau)</span>
            <span style={{ color: "#bbb" }}> ──┐</span>
            <br />
            <span style={{ color: "transparent" }}>{"P1 ──→ P2 ──→ P3"}</span>
            <span style={{ color: "#bbb" }}> └──→ </span>
            <span style={{ color: "#0F6E56", fontWeight: 600 }}>P5</span>
            <span style={{ color: "#888" }}> (Streamlit + RAG)</span>
            <span style={{ color: "#bbb" }}> ─┤</span>
            <br />
            <span style={{ color: "transparent" }}>{"P1 ──→ P2 ──→ P3 ──┬──→ P4 (Tableau) ──"}</span>
            <span style={{ color: "#bbb" }}>├──→ </span>
            <span style={{ color: "#5F5E5A", fontWeight: 600 }}>P6</span>
            <span style={{ color: "#888" }}> (Docs)</span>
          </div>
          <p style={{ fontSize: 11, color: "#888", margin: "8px 0 0", lineHeight: 1.5 }}>
            P1→P2→P3 is sequential (each needs previous data). P4 and P5 run in parallel. P6 is always last.
          </p>
        </div>

        {/* Early exit */}
        <div style={{ background: "#FAEEDA", borderRadius: 8, padding: "12px 18px", marginBottom: 20, border: "1px solid #FAC77544" }}>
          <p style={{ fontSize: 12, fontWeight: 600, color: "#854F0B", margin: "0 0 4px" }}>Early exit ramps</p>
          <p style={{ fontSize: 12, color: "#854F0B", margin: 0, lineHeight: 1.6, opacity: 0.85 }}>
            <span style={{ fontWeight: 600 }}>Minimum viable portfolio (10 days):</span> P1 + P3 + P4 — scrape data, score suburbs, publish Tableau dashboard. Covers SQL, geospatial, dashboarding.
            <br />
            <span style={{ fontWeight: 600 }}>Strong portfolio (15 days):</span> Add P2 — NLP analysis and listing honesty scoring. Covers everything above + NLP + feature engineering.
            <br />
            <span style={{ fontWeight: 600 }}>Exceptional portfolio (20 days):</span> Full build including P5 (RAG + Streamlit) + P6 (documentation). Covers every gap + demonstrates AI integration.
          </p>
        </div>

        {/* Phases */}
        <div style={{ marginBottom: 24 }}>
          {phases.map((p) => (
            <PhaseCard key={p.id} phase={p} isOpen={openPhases.has(p.id)} onToggle={() => toggle(p.id)} />
          ))}
        </div>

        {/* Repo structure */}
        <div style={{ background: "rgba(255,255,255,0.6)", borderRadius: 8, padding: "14px 18px", marginBottom: 16, border: "1px solid #e8e7e4" }}>
          <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", color: "#999", margin: "0 0 10px" }}>Final repo structure</p>
          <pre style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, lineHeight: 1.9, color: "#444", margin: 0, overflow: "auto" }}>
{`melbourne-rental-intelligence/
├── README.md
├── SETUP.md
├── LICENSE
├── data/
│   ├── raw/                     # scraped + downloaded files
│   ├── processed/               # cleaned CSVs for Tableau
│   └── melbourne.db             # SQLite database
├── scripts/
│   ├── 01_scrape_listings.py
│   ├── 02_fetch_ptv_data.py
│   ├── 03_fetch_osm_amenities.py
│   ├── 04_load_abs_data.py
│   ├── 05_create_db_schema.sql
│   └── 06_create_views.sql
├── notebooks/
│   ├── 01_data_exploration.ipynb
│   ├── 02_nlp_analysis.ipynb
│   ├── 03_geospatial_scoring.ipynb
│   └── 04_findings_and_visuals.ipynb
├── rag/
│   ├── config.py                # LLM provider abstraction
│   ├── query_parser.py          # intent + filter extraction
│   ├── retriever.py             # SQL-based retrieval
│   ├── prompt_templates.py      # system + context prompts
│   └── chain.py                 # end-to-end RAG chain
├── streamlit_app/
│   ├── app.py                   # main entry point
│   ├── pages/
│   │   ├── 01_suburb_finder.py
│   │   ├── 02_compare.py
│   │   ├── 03_buzzword_decoder.py
│   │   └── 04_ai_advisor.py
│   ├── utils/
│   └── requirements.txt
├── tableau/
│   ├── dashboard.twbx
│   └── screenshots/
└── docs/
    ├── methodology.md
    ├── blog_post.md
    └── architecture_diagram.png`}
          </pre>
        </div>

        {/* Final artefacts */}
        <div style={{ background: "rgba(255,255,255,0.6)", borderRadius: 8, padding: "14px 18px", border: "1px solid #e8e7e4" }}>
          <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", color: "#999", margin: "0 0 10px" }}>5 portfolio artefacts from one project</p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 12, color: "#444" }}>
            {[
              { icon: "01", name: "GitHub repo", desc: "Scripts, notebooks, clean commit history" },
              { icon: "02", name: "Tableau Public dashboard", desc: "Embeddable URL for resume + LinkedIn" },
              { icon: "03", name: "Live Streamlit app", desc: "RAG-powered suburb advisor" },
              { icon: "04", name: "Findings blog post", desc: "LinkedIn-ready data storytelling" },
              { icon: "05", name: "Loom walkthrough", desc: "3-minute video for applications" },
            ].map((a, i) => (
              <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: "8px 10px", background: "#f5f5f0", borderRadius: 6 }}>
                <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, fontWeight: 600, color: "#bbb", minWidth: 18 }}>{a.icon}</span>
                <div>
                  <p style={{ fontWeight: 600, color: "#1a1a1a", margin: 0, fontSize: 13 }}>{a.name}</p>
                  <p style={{ margin: 0, color: "#888", fontSize: 11 }}>{a.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
