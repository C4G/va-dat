import { ProjectSection } from '@/components/project-content';
export default function Home() {
  return (
    <>
      {(
        ['hero', 'about', 'goal', 'team', 'deliverables', 'lighthouse'] as const
      ).map((name) => (
        <ProjectSection key={name} name={name} original />
      ))}
    </>
  );
}
