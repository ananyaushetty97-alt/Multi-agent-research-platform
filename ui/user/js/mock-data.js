/**
 * Multi-Agent Research Platform - Mock Data Store
 * Matches backend schemas:
 * - api/main.py: TopicRequest, ReportResponse, /health, /scores
 * - graph/pipeline.py: ResearchState, 4-agent LangGraph flow
 * - evaluation/judge.py: grade_report (relevance, accuracy, clarity, overall, comment)
 * - memory/semantic_cache.py: cache lookup & hit/miss metadata
 */

const MOCK_PLATFORM_DATA = {
  systemHealth: {
    status: "ok",
    gateway: "Groq (Llama-3.3-70b-versatile)",
    fallbackGateway: "Ollama (llama3:8b local)",
    pipeline: "LangGraph 4-Agent Pipeline (Search -> Summarize -> Write -> Verify)",
    cache: "Redis Semantic Cache (Embedding Threshold 0.92)",
    ltm: "PostgreSQL + pgvector (1536-dim OpenProvenance)",
    guardrails: "Guardrails AI / PyRIT Red-Team Verified"
  },

  curatedInquiries: [
    {
      id: "microplastics",
      domain: "Marine Biology",
      title: "Impact of microplastics on marine fauna",
      abstract: "Examines trophic bioaccumulation velocities, cellular oxidative stress in apex predators, and 2024 bio-persistence benchmarks.",
      citationsCount: 7,
      verifiedScore: 9.6,
      image: "https://lh3.googleusercontent.com/aida-public/AB6AXuCeJqJ8fRy4NUNhbu4xPNT3iOLQDFW76ZxggSQ6UANL-eNPdgPCdD9YK4q0d9gxpYqwAvvzQYyai1az_qqZj3y572xrXS4xNNFRFGPr6hkGlTKARJy0obpbk4tpbSUA6o8NztckHRQHC567kvk0-n5Ea06Eb0sPOl9Jy2bFI2P9Dn7uAgYNkyCG_a74AaaL6KVZT0jaPGka_kBH02Y_P_W-KyJVW7dlxQKRJknVqZ5b5Y3IZnWmvlm4RQ"
    },
    {
      id: "quantum-error",
      domain: "Quantum Computing",
      title: "Quantum error mitigation & coherence",
      abstract: "Deconstructs probabilistic error cancellation, Clifford randomized benchmarking, and fault-tolerant syndrome fidelity.",
      citationsCount: 42,
      verifiedScore: 9.8,
      image: "https://lh3.googleusercontent.com/aida-public/AB6AXuCb0A_Zf8kebklnRsu3w5ImUWXKBhBiIlADmOTCSpigD_dQCU2r0mGtQ1vAD9vJjLy0ff64GLWtxXZlf5Mwsy5b27N1HSYdbvXy38XbbOKxj-fsmyzDgp31l2mgi7Nkuk7uUo0-ELiONJ0Nj0z8WBq5SeHw84V21ZBPxqE6u08tOx7UKDEFh9RJu-JUmd8oxOkaEBTzIopmhMvM93cn-J5kYvBGYn0LIc1FGncc36IfGMwPVgzxhB7nFQ"
    },
    {
      id: "solid-state-battery",
      domain: "Materials Science",
      title: "Solid-state electrolyte interfaces",
      abstract: "Evaluates sulfide vs oxide separator durability, mechanical stack pressure dynamics, and dendrite suppression kinetics.",
      citationsCount: 52,
      verifiedScore: 9.4,
      image: "https://lh3.googleusercontent.com/aida-public/AB6AXuBLP23NkwYX0If2lHqcI2k-nWRswuMI28YX42ZuoOh_PShmwb7ic-KtSi91MEZSgqZtQKQLdgNo5TFZy22tDUuP6nafAVmelhbNxaEhu5eDjftG0e-xlOO9JAZWigEDT0aNrQIQgdjDAFXtQYy-rMcaL6mLJkovj9AY20RLPPj7I-uwT-RHR3MSLZY6-cfOsPjkz0PidRfFuTQ3ZoJ-xPUZz6oLwzxmmXsxF3DhRDDOWKT0Fx3XG4zFVw"
    }
  ],

  historyItems: [
    {
      id: "microplastics",
      title: "Impact of microplastics on marine life",
      timeGroup: "Today",
      timestamp: "14:28",
      verified: true,
      score: 9.6,
      snippet: "…precipitating chronic gut obstruction, microplastics mimic natural zooplanktonic prey profiles across pelagic trophic chains…"
    },
    {
      id: "quantum-error",
      title: "Quantum Error Mitigation Review",
      timeGroup: "Today",
      timestamp: "11:15",
      verified: true,
      score: 9.8,
      snippet: "…probabilistic error cancellation yields sub-threshold syndrome fidelity when coupled with Clifford randomized benchmarking…"
    },
    {
      id: "crispr-analysis",
      title: "CRISPR Prime Editing Mechanisms",
      timeGroup: "Yesterday",
      timestamp: "Yesterday",
      verified: false,
      score: 8.9,
      snippet: "…reverse transcriptase fusion allows direct copying of edited sequence into genomic DNA without double-strand breaks…"
    },
    {
      id: "stellar-dynamics",
      title: "Stellar Dynamics & Dark Matter Halos",
      timeGroup: "Yesterday",
      timestamp: "Yesterday",
      verified: true,
      score: 9.5,
      snippet: "…phase-space distribution functions derived from Jeans equations under NFW profile boundary conditions…"
    },
    {
      id: "llm-consensus",
      title: "Epistemic Bounds in Multi-Agent Consensus",
      timeGroup: "Previous 7 days",
      timestamp: "3 days ago",
      verified: true,
      score: 9.7,
      snippet: "…evaluating self-consistency bounds and iterative revision convergence across asynchronous verifier agent nodes…"
    },
    {
      id: "solid-electrolyte",
      title: "Solid-State Electrolyte Interfaces",
      timeGroup: "Previous 7 days",
      timestamp: "5 days ago",
      verified: true,
      score: 9.3,
      snippet: "…electrochemical impedance spectroscopy reveals interphase impedance growth under high-current galvanostatic cycling…"
    }
  ],

  dossiers: {
    "microplastics": {
      topic: "Impact of microplastics on marine fauna and pelagic ecosystems",
      cached: false,
      seconds: 3.82,
      modelUsed: "Groq Llama-3.3-70b-versatile",
      revisionCount: 0,
      isVerified: true,
      score: {
        relevance: 10,
        accuracy: 9,
        clarity: 10,
        overall: 9.6,
        comment: "Rigorous, empirical synthesis strictly adhering to peer-reviewed evidence. Line-level citations correctly isolate laboratory assays from open ocean ecological observations."
      },
      agentTrace: [
        {
          agent: "Input Guardrail",
          icon: "security",
          status: "PASSED",
          detail: "Topic validated for safe academic research; zero prompt-injection or hazardous query markers detected.",
          timestamp: "0.12s"
        },
        {
          agent: "Search Agent",
          icon: "search",
          status: "COMPLETED",
          detail: "Queried academic corpus: NOAA Marine Debris, Nature Ecology, ScienceDirect, PNAS. Retrieved 14 relevant monographs.",
          timestamp: "1.42s"
        },
        {
          agent: "Summarize Agent",
          icon: "summarize",
          status: "COMPLETED",
          detail: "Extracted 7 core empirical findings, deduplicated chemical sorption metrics, and isolated conflicting calcification rates.",
          timestamp: "2.10s"
        },
        {
          agent: "Write Agent",
          icon: "edit_note",
          status: "COMPLETED",
          detail: "Synthesized 3 monograph sections, formatted citations [1]-[7], and structured executive synthesis.",
          timestamp: "3.20s"
        },
        {
          agent: "Verify Agent",
          icon: "verified",
          status: "VERIFIED",
          detail: "Fact-checked all claims against raw search corpus. Response: VERIFIED (0 revisions needed).",
          timestamp: "3.65s"
        },
        {
          agent: "LLM-as-a-Judge",
          icon: "gavel",
          status: "SCORED (9.6/10)",
          detail: "Strict rubric applied: Relevance 10, Accuracy 9, Clarity 10. Saved to logs/scores.jsonl.",
          timestamp: "3.82s"
        }
      ],
      sources: [
        {
          id: 1,
          domain: "marinedebris.noaa.gov",
          title: "NOAA Marine Debris Program — Benthic Ingestion & Histopathology Studies",
          url: "https://marinedebris.noaa.gov/reports/2023-microplastics-benthic",
          snippet: "Documented high-frequency microfragment penetration in intestinal villi resulting in chronic localized lesions and pseudo-satiation in benthic detritivores.",
          citationsCount: 3,
          isPeerReviewed: true
        },
        {
          id: 2,
          domain: "nature.com",
          title: "Nature Ecology & Evolution — Xenobiotic Leaching into Trophic Apex Regimes",
          url: "https://nature.com/articles/s41558-023-01824-w",
          snippet: "Secondary nanoplastics translocate across hemolymph barriers, precipitating chronic lipid peroxidation and compromised reproductive fecundity.",
          citationsCount: 2,
          isPeerReviewed: true
        },
        {
          id: 3,
          domain: "coralreefjournal.org",
          title: "Coral Reef Conservation Journal — Scleractinian Calcification Stress",
          url: "https://coralreefjournal.org/pub/2024/morphology-calcification",
          snippet: "Active mucus clearing cycles consume up to 35% of basal metabolic budget in hermatypic colonies exposed to floating polyethylene beads.",
          citationsCount: 1,
          isPeerReviewed: true
        },
        {
          id: 4,
          domain: "sciencedirect.com",
          title: "Environmental Pollution — Polymeric Sorbent Dynamics & PAH Desorption",
          url: "https://sciencedirect.com/science/article/pii/S026974912301",
          snippet: "Hydrophobic organic chemicals aggregate onto polyolefin surfaces at 100,000x seawater concentrations, desorbing rapidly under gut pH conditions.",
          citationsCount: 2,
          isPeerReviewed: true
        },
        {
          id: 5,
          domain: "who.int",
          title: "WHO Aquatic Health Brief — Global Microparticulate Dispersion Index",
          url: "https://who.int/water_sanitation_health/emerging_pollutants",
          snippet: "Preliminary global assessment identifying high-risk estuarine convergence zones; ongoing multi-center surveillance.",
          citationsCount: 1,
          isPeerReviewed: false
        },
        {
          id: 6,
          domain: "pnas.org",
          title: "PNAS — Trophic Transfer Kinetics Across Mesopelagic Food Webs",
          url: "https://pnas.org/doi/10.1073/pnas.2215984119",
          snippet: "Empirical tracer assays demonstrate microplastic bio-transfer from copepod primary consumers to lanternfish within 48 hours.",
          citationsCount: 1,
          isPeerReviewed: true
        },
        {
          id: 7,
          domain: "frontiersin.org",
          title: "Frontiers in Marine Science — Microplastic Epibiont Microbial Assemblages",
          url: "https://frontiersin.org/articles/10.3389/fmars.2023.1102",
          snippet: "The plastisphere harbors opportunistic pathogenic bacteria including Vibrio spp., altering natural microbial biofilms in coastal waters.",
          citationsCount: 1,
          isPeerReviewed: true
        }
      ]
    }
  },

  followUpExample: {
    question: "What does bioaccumulation mean?",
    answerParagraphs: [
      "Bioaccumulation designates the net gradual accumulation of a xenobiotic compound within the somatic tissues of an organism at a rate faster than it can be catabolized or excreted through metabolic depuration. In marine taxa, persistent organic pollutants (POPs) preferentially sequester into hydrophobic lipid reservoirs, establishing internal toxic concentrations that substantially surpass ambient hydrospheric levels throughout an individual specimen’s lifespan.",
      "While closely related, it is distinct from biomagnification, which strictly refers to the cumulative step-increase of contaminant loads propagated upward through contiguous trophic levels of the food web."
    ],
    distinction: {
      leftTitle: "Bioaccumulation",
      leftBody: "Intra-organismal dynamic. Occurs within a single individual's lifetime when absorption velocity (k1) exceeds metabolic elimination velocity (k2).",
      rightTitle: "Biomagnification",
      rightBody: "Inter-trophic chain process. Contaminant fugacity and mass-fraction scale consecutively across successive trophic tiers (from zooplankton to apex predators)."
    },
    suggestedChips: [
      "Compare bioaccumulation vs biomagnification",
      "Which marine species are most vulnerable?",
      "Quantify depuration half-lives in bivalves"
    ]
  }
};
