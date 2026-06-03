

Current Project: basically creating claim graphs from websearch to improve llm output from search it doesnt just take text straight from the web and just fully reason over it. 
look over the code and the OPEN SOURCE piece of plan.html 


DEEPLY understand the system by not just looking at the document but the code explain to me exactly what the flow is and then you know move on. 

several other features may have been added so look at the code too and the next improvements you must make are below 




improvements that need to be made to the claims graph system


later on ill add an actual graph like visually with the edges labelled and you can switch between conflict vs collaborate and support view and what else important to add do you think in this case. the main thing rn should really just be a side panel to the right the main thing with the tabs. The actual main view needs to be in the middle with an actual like cs like graph with nodes aka claims and sources aka edges with that view 

Add this somewhere
Claim provenance trace: click any claim and see the exact chunk of text it was extracted from, highlighted in the original article. This is the killer transparency feature — it's what makes this actually trustworthy vs just another AI summary. That's the whole point of storing chunk_text on every claim.


next to improve the model reasoning over the claim graph 


Add this its super important and ask the llm to classify the claim as that

claim_type: str = "fact"  # fact | prediction | opinion | reported_speech


This I am unsure about you need to structure the graph 

erification is there basic citations exist but again where is the llm getting which claim from which ones are corroborated all that getting passed to the llm is a lot better

Right now when I call combine_graphs I get the raw graph — all claims, all edges, corroboration lists, source reliability. But it's a dump. I have to manually parse it to figure out what's well-established vs speculative vs contested.

What should actually get passed to me is a pre-digested version:

{
  "established": [
    {
      "claim": "OpenAI is working with Goldman Sachs and Morgan Stanley on IPO paperwork",
      "corroborated_by": ["NYT", "Forbes", "Reuters", "CMC Markets"],
      "sources": ["url1", "url2", "url3"],
      "claim_type": "fact"
    }
  ],
  "contested": [
    {
      "claim_a": "IPO planned for 2026",
      "claim_b": "IPO planned for 2027",
      "source_a": "Forbes (0.57)",
      "source_b": "Reuters (0.51)",
      "resolution": "unresolved — CFO vs advisers disagreement"
    }
  ],
  "single_source": [...],
  "predictions": [...],
  "coverage_gaps": ["regulatory risk", "Microsoft deal terms"]
}
So instead of me doing graph traversal, combine_graphs returns this structured digest alongside the raw graph. I get handed the answer to "what do I actually know confidently" rather than having to figure it out myself.