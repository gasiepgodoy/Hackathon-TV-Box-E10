import { ArrowRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import ForgeSymbol from '../../assets/Forge-symbol.png';

interface WelcomePageProps {
  /** Enter the selection flow. */
  onStart: () => void;
}

/** Non-breaking space, used to keep the product name on a single line. */
const NBSP = String.fromCharCode(160);

/** Landing screen: clean Forge hero branding, intro text, and "Start now" CTA. */
export function WelcomePage({ onStart }: WelcomePageProps) {
  const { t } = useTranslation();

  // NBSP-bind "Forge Imager" so the title wraps before the product name, not mid-name.
  const heading = t('home.welcomeHeading').replace(/Forge\s*Imager/u, `Forge${NBSP}Imager`);

  return (
    <div className="welcome">
      <div className="welcome__content">
        <div className="welcome__brand">
          <img src={ForgeSymbol} alt="Multi-Forge" className="welcome__brand-logo" />
        </div>
        <h1 className="welcome__heading">{heading}</h1>
        <p className="welcome__intro">{t('home.welcomeIntro')}</p>
        <button type="button" className="welcome__cta" onClick={onStart}>
          {t('home.startNow')}
          <ArrowRight size={18} />
        </button>
      </div>
    </div>
  );
}
