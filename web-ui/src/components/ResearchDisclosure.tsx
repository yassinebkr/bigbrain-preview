import { Children, isValidElement, useState, type ReactNode } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';

// A marker for the disclosure's title; it never produces a native summary.
export function ResearchSummary({ children }: { children?: ReactNode; className?: string }) {
  return <>{children}</>;
}

export function ResearchDisclosure({ children, className = '', initiallyOpen = false, ...props }: { children?: ReactNode; className?: string; initiallyOpen?: boolean; 'aria-label'?: string }) {
  const [open, setOpen] = useState(initiallyOpen);
  const reduced = useReducedMotion();
  const parts = Children.toArray(children);
  const heading = parts.find((child) => isValidElement<{ children?: ReactNode }>(child) && child.type === ResearchSummary);
  const content = parts.filter((child) => child !== heading);
  return <Accordion type="single" collapsible value={open ? 'content' : ''} onValueChange={(value) => setOpen(!!value)}
    className={`research-disclosure ${className}`} {...props}>
    <AccordionItem value="content" className="border-0">
      <AccordionTrigger className="research-disclosure-trigger">{isValidElement<{ children?: ReactNode }>(heading) ? heading.props.children : null}</AccordionTrigger>
      <AccordionContent forceMount className="research-disclosure-body">
        <motion.div initial={false} animate={{ height: open ? 'auto' : 0, opacity: open ? 1 : 0 }}
          transition={{ duration: reduced ? 0 : .18 }} style={{ overflow: 'hidden' }} aria-hidden={!open}>
          <div inert={!open} className="research-disclosure-content">{content}</div>
        </motion.div>
      </AccordionContent>
    </AccordionItem>
  </Accordion>;
}
