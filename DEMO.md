# incimin.io - AI SRE Agent Demo Steps

## 1. Setup the Infrastructure
Ensure the full Docker Compose stack is running:
```bash
docker compose up -d
```

## 2. Seed the Data Planes
The topology (Memgraph) needs to be populated on a fresh start:
```bash
# Activate your virtual environment and install dependencies
source .venv/bin/activate
pip install -r requirements.txt

# Seed Memgraph (Topology)
python scripts/init_memgraph.py
```

## 3. Verify Health
Ensure the data planes are healthy and seeded:
```bash
python scripts/verify_data_planes.py
```

## 4. Run the Streamlit Agent UI
Set your Anthropic API key and start the frontend:
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
streamlit run src/ui/app.py
```
*(This will open the chat UI at `http://localhost:8501`)*

## 5. Execute the Demo Scenario
1. **Visual Topology:** Open Memgraph Lab at `http://localhost:3000` (Left window). Run the query:
   ```cypher
   MATCH path = (s:Service {name: 'frontend'})-[*BFS]->(target) RETURN path
   ```
2. **Inject Chaos:** Open a new terminal and intentionally crash the payment service to trigger latency:
   ```bash
   python scripts/chaos_inject.py --mode stop
   ```
3. **Agent Intervention:** In the Streamlit UI (Right window), enter the prompt:
   > *"Checkout latency is spiking. Investigate and give me a recommendation."*
4. **Observe:** The agent will autonomously trace the topology, check telemetry (ClickHouse), and output the root cause with its supporting evidence within 60 seconds!
5. **Recover:** Fix the chaos injection:
   ```bash
   python scripts/chaos_inject.py --mode recover
   ```
