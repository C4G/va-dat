// Project content migrated from the original VA-DAT website.
const sections = {
  hero: (
    <section id='hero' className='hero' aria-labelledby='hero-heading'>
      <div className='container'>
        <h1 id='hero-heading'>Automating Digital Accessibility</h1>
        <p className='hero-subtitle'>
          Building LLM-powered tools that make the web more accessible for
          people with visual impairments.
        </p>
        <p className='hero-partner'>
          A <strong>Computing for Good</strong> project at Georgia Tech, in
          partnership with{' '}
          <a href='https://dat.visionaid.org/'>
            Vision Aid Digital Accessibility Testing
          </a>
          .
        </p>
      </div>
      <div className='survey-container'>
        <a
          href='https://gtvault-my.sharepoint.com/:v:/g/personal/ahildebrandt3_gatech_edu/IQCbVzYIh9afSqegy5lM89HQAVDxiCbNS8i6-nFzSI2Egkg?nav=eyJyZWZlcnJhbEluZm8iOnsicmVmZXJyYWxBcHAiOiJTdHJlYW1XZWJBcHAiLCJyZWZlcnJhbFZpZXciOiJTaGFyZURpYWxvZy1MaW5rIiwicmVmZXJyYWxBcHBQbGF0Zm9ybSI6IldlYiIsInJlZmVycmFsTW9kZSI6InZpZXcifX0%3D&e=eeJ0dG'
          className='survey-btn'
          target='_blank'
          rel='noopener noreferrer'
        >
          Link to P6 Demo
        </a>
      </div>
    </section>
  ),
  about: (
    <section id='about' aria-labelledby='about-heading'>
      <div className='container'>
        <div className='section-header'>
          <div className='accent-bar' aria-hidden='true'></div>
          <h2 id='about-heading'>About the Project</h2>
        </div>
        <div className='about-content'>
          <p>
            We are partnering with the{' '}
            <strong>Vision Aid Digital Accessibility Testing Team</strong> to
            build LLM-powered tools that automate digital accessibility analysis
            and remediation. Our system analyzes webpage source code, identifies
            WCAG compliance issues, and generates structured reports with
            proposed fixes. A secondary tool will use these reports to automate
            code-level accessibility corrections.
          </p>
        </div>
      </div>
    </section>
  ),
  goal: (
    <section id='goal' aria-labelledby='goal-heading'>
      <div className='container'>
        <div className='section-header'>
          <div className='accent-bar' aria-hidden='true'></div>
          <h2 id='goal-heading'>Our Goal</h2>
        </div>
        <div className='goal-content'>
          <blockquote>
            <p>
              Reduce the time required to produce digital accessibility reports
              from hours to minutes using large language models, and automate
              the application of accessibility fixes to front-end code — making
              the web more accessible for people with visual impairments.
            </p>
          </blockquote>
        </div>
      </div>
    </section>
  ),
  team: (
    <section id='team' aria-labelledby='team-heading'>
      <div className='container'>
        <div className='section-header'>
          <div className='accent-bar' aria-hidden='true'></div>
          <h2 id='team-heading'>Our Team</h2>
          <p>
            Five Georgia Tech students working together to advance digital
            accessibility.
          </p>
        </div>
        <ul className='team-grid' role='list'>
          <li className='team-card'>
            <div className='team-card-initial' aria-hidden='true'>
              AH
            </div>
            <h3>Annika Hildebrandt</h3>
            <p className='team-role'>Preprocessing & Quality Assurance</p>
            <p className='team-desc'>
              Developed the HTML preprocessing approach that classifies
              accessibility checks as programmatic or LLM-requiring,
              dramatically reducing token costs. Created and iterated on
              element-specific LLM prompts across all three WCAG checklists.
              Evaluated pipeline precision/recall against the manual audit
              baseline and refined prompts to eliminate duplicate findings.
            </p>
          </li>
          <li className='team-card'>
            <div className='team-card-initial' aria-hidden='true'>
              AY
            </div>
            <h3>Andrew Yin</h3>
            <p className='team-role'>Infrastructure & Integration</p>
            <p className='team-desc'>
              Built the end-to-end pipeline from raw HTML input to structured
              accessibility report, integrating programmatic checks with LLM
              analysis. Handles server deployment on Render and extended the
              semantic checklists to cover forms and non-text content. Created
              the web interface for running audits.
            </p>
          </li>
          <li className='team-card'>
            <div className='team-card-initial' aria-hidden='true'>
              CN
            </div>
            <h3>Cole Niblett</h3>
            <p className='team-role'>Prompt Engineering & Evaluation</p>
            <p className='team-desc'>
              Built the modular LLM prompt pipeline for WCAG accessibility
              analysis, generating element-specific prompts tailored to
              preprocessed HTML inputs. Developed a multi-model evaluation
              harness comparing Claude and OpenAI outputs. Added OpenAI API
              support to the pipeline.
            </p>
          </li>
          <li className='team-card'>
            <div className='team-card-initial' aria-hidden='true'>
              NF
            </div>
            <h3>Nicholas Fulton</h3>
            <p className='team-role'>Web Scraping & Architecture</p>
            <p className='team-desc'>
              Implemented the link crawler with configurable depth for
              multi-page site analysis. Formalized the codebase with abstract
              base classes and PyPI-compatible package structure for long-term
              sustainability. Ran initial experiments with open-source models to
              benchmark against frontier LLMs.
            </p>
          </li>
          <li className='team-card'>
            <div className='team-card-initial' aria-hidden='true'>
              MM
            </div>
            <h3>Mariana Mendez</h3>
            <p className='team-role'>Manual Audit & Accessibility</p>
            <p className='team-desc'>
              Completed the manual WCAG 2.1 AA accessibility audit of Vision Aid
              pages, establishing the ground-truth baseline for evaluating
              automated output. Made HTML/CSS accessibility improvements to the
              project site. Updated LLM prompts and the report generator to
              produce specific before/after HTML fix recommendations.
            </p>
          </li>
        </ul>
      </div>
    </section>
  ),
  deliverables: (
    <section id='deliverables' aria-labelledby='deliverables-heading'>
      <div className='container'>
        <div className='section-header'>
          <div className='accent-bar' aria-hidden='true'></div>
          <h2 id='deliverables-heading'>Deliverables</h2>
          <p>The key outputs our team is building for Vision Aid.</p>
        </div>
        <ol className='deliverables-list'>
          <li>
            <strong>Accessibility Report Generator</strong> — Analyze static
            webpage code for WCAG compliance issues and produce structured
            reports with proposed fixes.
          </li>
          <li>
            <strong>Automated Webpage Editor</strong> — Generate code-level
            fixes for identified accessibility issues, enabling rapid
            remediation.
          </li>
          <li>
            <strong>Chrome Browser Extension</strong>
            <span className='stretch'>Stretch Goal</span> — Apply accessibility
            fixes directly in-browser for end users.
          </li>
        </ol>
      </div>
    </section>
  ),
  lighthouse: (
    <section id='lighthouse' aria-labelledby='lighthouse-heading'>
      <div className='container'>
        <div className='section-header'>
          <div className='accent-bar' aria-hidden='true'></div>
          <h2 id='lighthouse-heading'>Lighthouse Scores</h2>
          <p>
            Measuring the quality of this website across four key categories.
          </p>
        </div>
        <div className='lighthouse-grid' role='list'>
          <div
            className='lighthouse-card'
            role='listitem'
            aria-label='Performance score: 92 out of 100'
          >
            <h3 aria-hidden='true'>Performance</h3>
            <span className='lighthouse-score' aria-hidden='true'>
              92
            </span>
          </div>
          <div
            className='lighthouse-card'
            role='listitem'
            aria-label='Accessibility score: 96 out of 100'
          >
            <h3 aria-hidden='true'>Accessibility</h3>
            <span className='lighthouse-score' aria-hidden='true'>
              96
            </span>
          </div>
          <div
            className='lighthouse-card'
            role='listitem'
            aria-label='Best Practices score: 100 out of 100'
          >
            <h3 aria-hidden='true'>Best Practices</h3>
            <span className='lighthouse-score' aria-hidden='true'>
              100
            </span>
          </div>
          <div
            className='lighthouse-card'
            role='listitem'
            aria-label='SEO score: 100 out of 100'
          >
            <h3 aria-hidden='true'>SEO</h3>
            <span className='lighthouse-score' aria-hidden='true'>
              100
            </span>
          </div>
        </div>
        <p className='lighthouse-note'>
          Historical scores measured via Chrome DevTools Lighthouse on the
          original home page, not this React build.
        </p>
      </div>
    </section>
  ),
};
export function ProjectSection({
  name,
  original = false,
}: {
  name: keyof typeof sections;
  original?: boolean;
}) {
  return original ? (
    sections[name]
  ) : (
    <div className='project-copy'>{sections[name]}</div>
  );
}
