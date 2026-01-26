# =============================
# RESUME SECTION HEADERS
# =============================

SKILL_HEADERS = [
    "skills",
    "technical skills",
    "tech stack",
    "technologies"
]

PROJECT_HEADERS = [
    "projects",
    "personal projects",
    "academic projects"
]

EXPERIENCE_HEADERS = [
    "experience",
    "work experience",
    "internships",
    "professional experience"
]


# =============================
# JD SECTION HEADERS
# =============================

REQUIRED_HEADERS = [
    "requirements",
    "required skills",
    "must have",
    "minimum qualifications",
    "what you will need"
]

PREFERRED_HEADERS = [
    "preferred skills",
    "nice to have",
    "good to have",
    "preferred qualifications",
    "bonus"
]


# =============================
# SKILL VOCABULARY (CONTROLLED)
# =============================
# NOTE:
# - lowercase only
# - normalized canonical names
# - no aliases here (aliases go into implications)

SKILL_VOCABULARY = [

    # -------------------------
    # Programming Languages
    # -------------------------
    "python",
    "java",
    "c++",
    "javascript",
    "sql",

    # -------------------------
    # Core CS Fundamentals
    # -------------------------
    "data structures",
    "algorithms",
    "object oriented programming",
    "dbms",
    "operating systems",
    "networking",

    # -------------------------
    # Data & AI
    # -------------------------
    "machine learning",
    "deep learning",
    "nlp",
    "data science",
    "statistics",

    # -------------------------
    # GenAI / LLM
    # -------------------------
    "llm",
    "retrieval augmented generation",
    "conversational ai",
    "prompt engineering",

    # -------------------------
    # Frameworks & Libraries
    # -------------------------
    "tensorflow",
    "pytorch",
    "scikit-learn",
    "numpy",
    "pandas",

    # -------------------------
    # Backend & APIs
    # -------------------------
    "fastapi",
    "flask",
    "rest api",

    # -------------------------
    # DevOps / MLOps
    # -------------------------
    "docker",
    "kubernetes",
    "ci/cd",
    "mlops",
    "model deployment",

    # -------------------------
    # Vector Databases
    # -------------------------
    "chromadb",
    "faiss",
    "vector database",

    # -------------------------
    # Version Control & OS
    # -------------------------
    "git",
    "github",
    "linux",

    # -------------------------
    # Cloud
    # -------------------------
    "aws",
    "azure",
    "gcp"
]


# =============================
# SKILL IMPLICATIONS
# =============================
# Purpose:
# - infer higher-level skills from tools/libraries
# - improve recall without hallucination

SKILL_IMPLICATIONS = {

    # -------------------------
    # Machine Learning
    # -------------------------
    "machine learning": {
        "machine learning",
        "ml",
        "scikit-learn",
        "sklearn",
        "xgboost",
        "random forest",
        "svm",
        "classification",
        "regression",
        "feature engineering"
    },

    # -------------------------
    # Deep Learning
    # -------------------------
    "deep learning": {
        "deep learning",
        "tensorflow",
        "pytorch",
        "keras",
        "cnn",
        "rnn",
        "lstm"
    },

    # -------------------------
    # NLP
    # -------------------------
    "nlp": {
        "nlp",
        "natural language processing",
        "spacy",
        "nltk",
        "tf-idf",
        "tokenization",
        "bert",
        "transformer"
    },

    # -------------------------
    # Data Science
    # -------------------------
    "data science": {
        "data science",
        "pandas",
        "numpy",
        "matplotlib",
        "seaborn",
        "jupyter",
        "data analysis"
    },

    # -------------------------
    # LLM / GenAI
    # -------------------------
    "llm": {
        "llm",
        "large language model",
        "chatbot",
        "conversational ai",
        "prompt engineering"
    },

    "retrieval augmented generation": {
        "rag",
        "retrieval augmented generation",
        "vector search",
        "semantic search"
    },

    # -------------------------
    # Vector Databases
    # -------------------------
    "vector database": {
        "chromadb",
        "faiss",
        "vector database",
        "embeddings"
    },

    # -------------------------
    # MLOps / Deployment
    # -------------------------
    "model deployment": {
        "model deployment",
        "production model",
        "inference api",
        "ml service"
    },

    "ci/cd": {
        "ci/cd",
        "cicd",
        "pipeline",
        "github actions"
    },

    # -------------------------
    # CS Fundamentals
    # -------------------------
    "data structures": {
        "linked list",
        "stack",
        "queue",
        "tree",
        "graph",
        "hashmap",
        "array"
    },

    "object oriented programming": {
        "oops",
        "object oriented",
        "class",
        "object",
        "inheritance",
        "polymorphism",
        "encapsulation"
    },

    "dbms": {
        "dbms",
        "sql",
        "mysql",
        "postgresql",
        "mongodb",
        "database"
    }
}
