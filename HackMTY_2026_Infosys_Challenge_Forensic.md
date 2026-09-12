Challenge Tracks 



# ** The Forensic Auditor** 

|Section|Content|
|---|---|
|About your company|Infosys is a global technology and consulting company with deep experience in finance,<br>accounting, and risk. From its Monterrey center it has done bookkeeping, compliance, and<br>fraud-investigation work for clients across the Americas since 2007.|
|The problem today|Invoice fraud in Mexico is not a neat list of flagged rows. It is a scheme hidden inside a<br>real company's books: a fake supplier billing for work never done, a kickback routed<br>through a shell company, or sales faked to inflate the numbers. Mexico's tax authority,<br>SAT, publishes a blacklist of fake-invoice companies under Article 69-B, but by the time a<br>supplier appears on it, the company has already claimed the deductions and is on the<br>hook. Today's tools flag odd items one at a time and leave a person to connect them.<br>Nobody follows the money all the way, nobody builds the proof, and honest suppliers who<br>simply look odd get accused too.|
|The big challenge|Given a company's books and only the hint that something is wrong, can an AI agent find<br>the fraud, follow the money, and prove it, without accusing anyone it cannot back up?|
|Possible approaches|(1) Investigate step by step: form a theory, search the ledger, invoices, and bank records,<br>follow a lead, and change course when it dead-ends. (2) Use simple detectors (blacklisted<br>suppliers, payments that do not match invoices, money that moves in a circle) to point the<br>agent at what is worth digging into. (3) Build an evidence trail for every accusation and<br>refuse to name a supplier it cannot back with a clear rule broken and a peso amount.|
|Resources for hackers|Teams build on real, free resources that exist online. SAT publishes the official Article 69-<br>B list of companies that issue fake invoices (EFOS), a real, downloadable Mexican<br>dataset, along with the CFDI 4.0 invoice schemas. IBM AMLSim (open-source) generates<br>the money-flow rings and shell-company patterns behind kickbacks and round-tripping.<br>Public financial-fraud datasets, such as the IEEE-CIS set on Kaggle, give baselines for the<br>anomaly checks. Teams assemble a company data estate from these pieces, a ledger,<br>invoices, bank records, and a supplier list, then build the investigation loop. Note on tools:<br>this track makes many AI calls per investigation, so a local model (Ollama) with caching is<br>safer than the Gemini free tier alone, which can hit daily limits.|
|What to build|A forensic agent that investigates records it has never seen and hands in a case file: the<br>scheme, the suppliers involved, the evidence trail, and the peso amount, plus a short list of<br>leads it chose not to chase and why. Deliver working code and a 3-minute live demo<br>where judges hide a fresh scheme in the data, the agent traces the money on screen, then<br>answers one surprise question about its reasoning.|
|Why it matters|Every peso lost to fake invoices is taken from an honest business and the public purse,<br>and every supplier wrongly accused loses a customer for no reason. An agent that<br>investigates and proves, instead of just flagging, is the difference between a report that<br>falls apart and a case a company can act on. This is the forensic work Infosys does at<br>scale, and proving before accusing is what separates a real auditor from a guesser.|
|Judging criteria|**Results:**on records it has never seen, how much hidden fraud does the agent find and<br>correctly prove?<br>**Judgment:**does it refuse to accuse suppliers it cannot back up, and can it defend a<br>finding when a judge asks?<br>**Feasibility:**could a real finance or audit team trust and use this?<br>**Clarity:**is the case file easy to follow, with a clear money trail?|



3 of 5 

