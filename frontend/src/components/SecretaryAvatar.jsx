/**
 * 有表情的秘书头像
 * mood: idle（默认，定时眨眼） | thinking（眼睛转圈） | happy（笑眼 + 咧嘴）
 */
export default function SecretaryAvatar({ size = 40, mood = 'idle', className = '' }) {
  const eye = Math.max(7, Math.round(size * 0.22))
  const pupil = Math.max(3, Math.round(size * 0.1))
  const moodClass = mood === 'thinking' ? 'sec-thinking' : mood === 'happy' ? 'sec-happy' : ''

  return (
    <span
      className={`sec-avatar relative inline-block flex-none bg-gradient-to-br from-brand-500 to-brand-700 shadow-[0_4px_12px_rgba(79,70,229,0.28)] ${moodClass} ${className}`}
      style={{ width: size, height: size, borderRadius: Math.round(size * 0.32) }}
      aria-hidden="true"
    >
      <span
        className="absolute flex"
        style={{ top: Math.round(size * 0.28), left: Math.round(size * 0.19), gap: Math.round(size * 0.14) }}
      >
        {[0, 1].map((index) => (
          <span
            key={index}
            className="sec-eye flex items-center justify-center bg-white"
            style={{ width: eye, height: eye, borderRadius: '50%' }}
          >
            <span className="sec-pupil-orbit">
              <span
                className="block rounded-full"
                style={{ width: pupil, height: pupil, background: '#1e1b4b' }}
              />
            </span>
          </span>
        ))}
      </span>
      <span
        className="sec-mouth absolute"
        style={{
          top: Math.round(size * 0.6),
          left: Math.round(size * 0.34),
          width: Math.round(size * 0.32),
          height: Math.round(size * 0.16),
          border: '2px solid transparent',
          borderBottomColor: 'rgba(255,255,255,0.95)',
          borderRadius: '50%',
        }}
      />
    </span>
  )
}
