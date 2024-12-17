import { writable, derived } from 'svelte/store';
import { browser } from '$app/environment';

const TRANSLATIONS: Record<string, Record<string, string>> = {
    'en-US': {
        'hero.title': 'CONTRACTS IN THE FUTURE',
        'hero.subtitle': "It's time to simplify your contract drafting",
        'hero.cta': 'Try it now',
        'information.title': 'What We Do',
        'information.description': 'We help you draft, learn and fix contracts ',
        'information.descriptionBold': 'with AI',
        'work.title': 'HOW IT WORKS',
        'work.features.0.title': 'Not ChatGPT',
        'work.features.0.description': 'Our model was trained on millions (seriously!) of legal clauses',
        'work.features.1.title': 'Secure Document Management',
        'work.features.1.description': 'Enterprise-grade security for your sensitive legal documents',
        'work.features.2.title': 'Collaborative Editing',
        'work.features.2.description': 'Real-time collaboration tools for team contract review',
        'work.features.3.title': 'Automated Learning',
        'work.features.3.description': 'AI-driven insights and recommendations for contract optimization',
        'faq.title': 'FREQUENTLY ASKED QUESTIONS',
        'faq.q1': 'What is Cicero?',
        'faq.a1': 'Cicero is an AI-powered platform for drafting, learning, and fixing contracts.',
        'faq.q2': 'How does it work?',
        'faq.a2': 'Upload your contract or start from scratch, and our AI will help you draft, understand, and improve it.',
        'faq.q3': 'Is it secure?',
        'faq.a3': 'Yes, we use industry-standard encryption and security measures to protect your data.',
        'faq.q4': 'Who owns the copyright?',
        'faq.a4': 'You do.',
        'newsletter.title': 'Newsletter',
        'newsletter.description': 'Subscribe to our newsletter',
        'newsletter.button': 'Subscribe',
        'footer.aboutUs': 'About us',
        'footer.blog': 'Blog',
        'footer.contactUs': 'Contact us',
        'footer.termsPrivacy': 'Terms & privacy',
        'footer.cookieSettings': 'Cookie settings',
        'footer.rights': 'All rights reserved',
        'footer.privacyPolicy': 'Privacy Policy',
        'about.title': 'About',
        'about.description': 'is an advanced AI-powered platform designed specifically for legal professionals, focusing on drafting, learning, and improving contracts and legal documents.',
        'about.mission.title': 'Our Mission',
        'about.mission.description': 'We aim to transform the way legal professionals work with documents by providing an intelligent, efficient, and user-friendly platform.',
        'about.features.title': 'What Makes',
        'about.features.different': 'Different',
        'about.features.legalFocus': 'Specialized Legal Focus',
        'about.features.legalFocus.1': 'Expert in drafting and analyzing legal clauses',
        'about.features.legalFocus.2': 'Comprehensive contract creation capabilities',
        'about.features.legalFocus.3': 'Step-by-step document building approach',
        'about.features.legalFocus.4': 'Support for both Portuguese and English legal documents',
        'about.features.documentHandling': 'Smart Document Handling',
        'about.features.documentHandling.1': 'Intelligent clause suggestions',
        'about.features.documentHandling.2': 'Context-aware document drafting',
        'about.features.documentHandling.3': 'Ability to handle complex legal terminology',
        'about.features.documentHandling.4': 'Efficient document organization',
        'about.features.professional': 'Professional Features',
        'about.features.professional.1': 'Multi-language support (PT-BR and EN-US)',
        'about.features.professional.2': 'Secure document handling',
        'about.features.professional.3': 'Clean, intuitive interface',
        'about.features.professional.4': 'Progressive Web App for mobile access',
        'about.features.technical': 'Technical Excellence',
        'about.features.technical.1': 'Built on advanced language models',
        'about.features.technical.2': 'Docker-based deployment',
        'about.features.technical.3': 'Enterprise-grade security',
        'about.features.technical.4': 'Scalable architecture',
        'about.bestPractices.title': 'Best Practices for Using',
        'about.bestPractices.1': 'Start a new chat for each distinct task',
        'about.bestPractices.2': 'Break down complex documents into components',
        'about.bestPractices.3': 'Use specific terms like "formal" or "informal"',
        'about.bestPractices.4': 'Take advantage of legal expertise',
        'about.commitment.title': 'Our Commitment',
        'about.commitment.1': 'Maintaining the highest standards of legal accuracy',
        'about.commitment.2': 'Continuous improvement of our AI capabilities',
        'about.commitment.3': 'Protecting user privacy and data security',
        'about.commitment.4': 'Providing responsive support to our users',
        'about.contact.title': 'Contact Us',
        'about.contact.description': 'For support or inquiries'
    },
    'pt-BR': {
        'hero.title': 'CONTRATOS NO FUTURO',
        'hero.subtitle': 'Chegou a hora de simplificar seus contratos',
        'hero.cta': 'Comece agora',
        'information.title': 'O Que Fazemos',
        'information.description': 'Usamos IA para ajudar você a criar, entender e aprimorar seus contratos ',
        'information.descriptionBold': 'com IA',
        'work.title': 'COMO FUNCIONA',
        'work.features.0.title': 'Muito além do ChatGPT',
        'work.features.0.description': 'Nossa IA foi treinada com milhões de cláusulas jurídicas reais',
        'work.features.1.title': 'Segurança Total',
        'work.features.1.description': 'Proteção de nível empresarial para seus documentos confidenciais',
        'work.features.2.title': 'Trabalho em Equipe',
        'work.features.2.description': 'Colabore em tempo real na revisão dos seus contratos',
        'work.features.3.title': 'Aprendizado Inteligente',
        'work.features.3.description': 'Sugestões personalizadas para melhorar seus contratos',
        'faq.title': 'DÚVIDAS FREQUENTES',
        'faq.q1': 'O que é o Cicero?',
        'faq.a1': 'O Cicero é uma plataforma que usa Inteligência Artificial para ajudar você a criar, entender e aprimorar seus contratos.',
        'faq.q2': 'Como funciona?',
        'faq.a2': 'É simples: envie seu contrato ou comece do zero. Nossa IA vai te ajudar a criar, entender e melhorar cada detalhe.',
        'faq.q3': 'É seguro?',
        'faq.a3': 'Com certeza! Utilizamos criptografia avançada e as melhores práticas de segurança do mercado para proteger seus dados.',
        'faq.q4': 'Quem é o dono dos direitos autorais?',
        'faq.a4': 'Você, sempre.',
        'newsletter.title': 'Fique por dentro',
        'newsletter.description': 'Receba nossas novidades e dicas exclusivas',
        'newsletter.button': 'Quero receber',
        'footer.aboutUs': 'Quem somos',
        'footer.blog': 'Blog',
        'footer.contactUs': 'Fale conosco',
        'footer.termsPrivacy': 'Termos e privacidade',
        'footer.cookieSettings': 'Preferências de cookies',
        'footer.rights': 'Todos os direitos reservados',
        'footer.privacyPolicy': 'Política de Privacidade',
        'about.title': 'Sobre',
        'about.description': 'é uma plataforma avançada baseada em IA, projetada especificamente para profissionais do direito, focada na elaboração, aprendizado e aprimoramento de contratos e documentos jurídicos.',
        'about.mission.title': 'Nossa Missão',
        'about.mission.description': 'Nosso objetivo é transformar a maneira como os profissionais do direito trabalham com documentos, fornecendo uma plataforma inteligente, eficiente e amigável.',
        'about.features.title': 'O que Torna o',
        'about.features.different': 'Diferente',
        'about.features.legalFocus': 'Foco Jurídico Especializado',
        'about.features.legalFocus.1': 'Especialista em elaboração e análise de cláusulas jurídicas',
        'about.features.legalFocus.2': 'Capacidades abrangentes de criação de contratos',
        'about.features.legalFocus.3': 'Abordagem passo a passo na construção de documentos',
        'about.features.legalFocus.4': 'Suporte para documentos jurídicos em português e inglês',
        'about.features.documentHandling': 'Gerenciamento Inteligente de Documentos',
        'about.features.documentHandling.1': 'Sugestões inteligentes de cláusulas',
        'about.features.documentHandling.2': 'Redação contextualizada de documentos',
        'about.features.documentHandling.3': 'Capacidade de lidar com terminologia jurídica complexa',
        'about.features.documentHandling.4': 'Organização eficiente de documentos',
        'about.features.professional': 'Recursos Profissionais',
        'about.features.professional.1': 'Suporte multilíngue (PT-BR e EN-US)',
        'about.features.professional.2': 'Manipulação segura de documentos',
        'about.features.professional.3': 'Interface limpa e intuitiva',
        'about.features.professional.4': 'Aplicativo Web Progressivo para acesso móvel',
        'about.features.technical': 'Excelência Técnica',
        'about.features.technical.1': 'Construído com modelos de linguagem avançados',
        'about.features.technical.2': 'Implantação baseada em Docker',
        'about.features.technical.3': 'Segurança de nível empresarial',
        'about.features.technical.4': 'Arquitetura escalável',
        'about.bestPractices.title': 'Melhores Práticas para Usar o',
        'about.bestPractices.1': 'Inicie um novo chat para cada tarefa distinta',
        'about.bestPractices.2': 'Divida documentos complexos em componentes',
        'about.bestPractices.3': 'Use termos específicos como "formal" ou "informal"',
        'about.bestPractices.4': 'Aproveite a expertise jurídica',
        'about.commitment.title': 'Nosso Compromisso',
        'about.commitment.1': 'Manutenção dos mais altos padrões de precisão jurídica',
        'about.commitment.2': 'Melhoria contínua de nossas capacidades de IA',
        'about.commitment.3': 'Proteção da privacidade e segurança dos dados dos usuários',
        'about.commitment.4': 'Fornecimento de suporte ágil aos nossos usuários',
        'about.contact.title': 'Entre em Contato',
        'about.contact.description': 'Para suporte ou dúvidas'
    }
};

export const currentLang = writable(browser ? localStorage.getItem('preferredLanguage') || 'en-US' : 'en-US');

export const t = derived(currentLang, (lang) => {
    return (key: string) => {
        const translation = TRANSLATIONS[lang]?.[key];
        if (!translation) {
            console.warn(`Missing translation for key: ${key} in language: ${lang}`);
            return key;
        }
        return translation;
    };
});

/**
 * Toggles the application language between English (en-US) and Portuguese (pt-BR).
 * 
 * @remarks
 * This function switches between two supported languages and persists the selection
 * in localStorage. It also updates the reactive language store.
 * 
 * @returns void
 * 
 * @throws Does not execute if running in non-browser environment
 * 
 * @example
 * ```typescript
 * toggleLanguage(); // If current is 'en-US', switches to 'pt-BR'
 * toggleLanguage(); // If current is 'pt-BR', switches to 'en-US'
 * ```
 */
export function toggleLanguage(): void {
    if (!browser) return;
    
    const current = localStorage.getItem('preferredLanguage') || 'en-US';
    const newLang = current === 'en-US' ? 'pt-BR' : 'en-US';
    
    localStorage.setItem('preferredLanguage', newLang);
    currentLang.set(newLang);
}
