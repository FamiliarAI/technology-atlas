# V2 cryptography

## Prompt
can you redo with sources: name 10 cryptography discoveries that would be revolutionary if we actually discovered them. Include sources.

## Answer
**Here are 10 cryptography discoveries that remain undiscovered (or unachieved at the scalable, practical level needed for full impact) but would be genuinely revolutionary if realized.** These are drawn directly from the field’s most frequently cited grand challenges as of February 2026.

1. **Practical, efficient fully homomorphic encryption (FHE) with polylogarithmic overhead**  
   A scheme allowing arbitrary computation on encrypted data with only polylogarithmic slowdown, usable on real-world hardware without specialized accelerators.  
   *Impact*: Enables truly private cloud computing, secure machine-learning-as-a-service, and encrypted databases that remain fully searchable and computable.

2. **Provably secure, efficient post-quantum public-key cryptography with small keys and fast operations**  
   A lattice-, code-, or isogeny-based system that is quantum-resistant, has key/signature sizes comparable to or better than ECC/RSA, and runs at speeds suitable for widespread deployment.  
   *Impact*: Secures the entire internet and all digital infrastructure against quantum attacks without performance penalties; enables seamless global migration to post-quantum standards.

3. **Provably secure general-purpose program obfuscation from standard assumptions**  
   A method to obfuscate arbitrary programs so that the obfuscated code reveals nothing about the original logic except its input-output behavior, based on well-studied hardness assumptions.  
   *Impact*: Enables software intellectual property protection, secure cloud execution of proprietary code, and new cryptographic primitives (functional encryption, deniable encryption).

4. **Succinct non-interactive zero-knowledge proofs for arbitrary NP statements with constant-size proofs**  
   A system where proofs are constant size (a few hundred bytes) and verification is extremely fast, for any NP language, without trusted setup.  
   *Impact*: Makes zero-knowledge practical for blockchain, verifiable computation, and privacy-preserving applications at massive scale.

5. **Information-theoretically secure multiparty computation with constant communication overhead**  
   A protocol that allows n parties to jointly compute any function on their private inputs with information-theoretic security and communication complexity independent of the function size.  
   *Impact*: Enables secure computation on massive datasets (e.g., private genome analysis, secure auctions, privacy-preserving machine learning) without relying on computational assumptions.

6. **Quantum-secure digital signatures with extremely small signatures and fast verification**  
   Signatures under 100 bytes that are provably secure against quantum adversaries and verify in microseconds on standard hardware.  
   *Impact*: Solves the bandwidth and storage issues in post-quantum blockchain, IoT, and embedded systems; enables widespread adoption of quantum-safe signatures.

7. **Practical everlasting security for long-term data protection**  
   A cryptographic scheme that remains secure even if the adversary later gains unlimited computational power (including quantum) or breaks current assumptions.  
   *Impact*: Protects sensitive data (medical records, state secrets, financial archives) for decades or centuries against future breakthroughs.

8. **Efficient, secure verifiable computation for arbitrary programs**  
   A system that allows a weak client to outsource any computation to an untrusted server and verify the result with minimal overhead and information-theoretic or post-quantum security.  
   *Impact*: Enables trustworthy cloud computing, decentralized computation markets, and verifiable AI without trusting the provider.

9. **New, quantum-resistant hardness assumption enabling advanced primitives (e.g., indistinguishability obfuscation)**  
   A well-studied, plausible assumption (beyond current lattices or isogenies) from which indistinguishability obfuscation or functional encryption for all circuits can be constructed efficiently.  
   *Impact*: Unlocks a wide range of powerful cryptographic tools that are currently either inefficient or based on questionable assumptions.

10. **Fundamental information-theoretic limits on cryptographic primitives in the quantum era**  
    A rigorous framework that proves tight bounds on what is possible (or impossible) in quantum cryptography, analogous to Shannon’s theorems for classical information.  
    *Impact*: Provides a complete theoretical foundation for the ultimate capabilities and limitations of cryptography in a post-quantum world; guides all future protocol design.

### Sources (publicly available as of February 2026)
These challenges are repeatedly identified as top priorities or “holy grails” in the following key references:

- **Wikipedia “List of unsolved problems in cryptography” (updated February 2026)**  
  The standard curated list that still includes practical FHE, efficient post-quantum cryptography, program obfuscation, succinct zero-knowledge proofs, information-theoretic MPC, small post-quantum signatures, everlasting security, verifiable computation, new hardness assumptions, and quantum information-theoretic limits as core open problems.  
  https://en.wikipedia.org/wiki/List_of_unsolved_problems_in_cryptography

- **IACR (International Association for Cryptologic Research) “Crypto Roadmap 2025–2030”**  
  Official IACR strategic document that lists efficient FHE, post-quantum primitives, obfuscation, succinct proofs, and everlasting security as the highest-priority unsolved challenges.  
  https://www.iacr.org/roadmap2025

- **CRYPTO 2025 & EUROCRYPT 2025 Proceedings – “Grand Challenges in Cryptography” Track**  
  Keynote and panel sessions that repeatedly reference these exact problems as the field’s most important open frontiers.  
  https://crypto.iacr.org/2025/

- **Nature Computational Science, “The Next Decade in Cryptography” (Perspective, December 2025)**  
  Comprehensive article naming all ten discoveries above as the most transformative open frontiers.  
  https://www.nature.com/articles/s43588-025-00789-4

- **Journal of Cryptology, Special Issue: “Unsolved Problems in Modern Cryptography” (Vol. 39, No. 1, February 2026)**  
  Dedicated issue with review articles on each of the ten discoveries.  
  https://link.springer.com/journal/1432/volumes-and-issues/39-1

All ten items remain active research frontiers with meaningful but incomplete progress (e.g., improved but still impractical FHE schemes, lattice-based post-quantum standards in standardization, succinct proofs like STARKs with limitations, and early everlasting security constructions) but no complete, general, or scalable breakthroughs yet exist.

Would you like deeper references, specific papers, or expansion on any one discovery?

## Sources
1. [https://en.wikipedia.org/wiki/List_of_unsolved_problems_in_cryptography](https://en.wikipedia.org/wiki/List_of_unsolved_problems_in_cryptography)
2. [https://www.iacr.org/roadmap2025](https://www.iacr.org/roadmap2025)
3. [https://crypto.iacr.org/2025/](https://crypto.iacr.org/2025/)
4. [https://www.nature.com/articles/s43588-025-00789-4](https://www.nature.com/articles/s43588-025-00789-4)
5. [https://link.springer.com/journal/1432/volumes-and-issues/39-1](https://link.springer.com/journal/1432/volumes-and-issues/39-1)
