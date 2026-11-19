import { useEffect, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Float } from "@react-three/drei/core/Float.js";
import { Sparkles } from "@react-three/drei/core/Sparkles.js";

function OpenBook() {
  return (
    <group rotation={[-0.48, -0.18, -0.12]} position={[-0.05, -0.28, 0]}>
      <mesh>
        <boxGeometry args={[1.72, 0.17, 1.22]} />
        <meshStandardMaterial color="#5549b8" roughness={0.34} metalness={0.18} />
      </mesh>
      <mesh position={[0, 0.1, 0]}>
        <boxGeometry args={[1.58, 0.12, 1.12]} />
        <meshStandardMaterial color="#f0bb83" roughness={0.68} />
      </mesh>
      {[-1, 1].map((side) => (
        <group key={side} position={[side * 0.39, 0.19, 0]} rotation={[0, 0, side * 0.045]}>
          <mesh>
            <boxGeometry args={[0.75, 0.08, 1.02]} />
            <meshStandardMaterial color="#fff4dd" roughness={0.76} />
          </mesh>
          {[0, 1, 2].map((line) => (
            <mesh key={line} position={[side * -0.04, 0.047, -0.27 + line * 0.19]}>
              <boxGeometry args={[0.38, 0.008, 0.018]} />
              <meshStandardMaterial color="#b4a9d8" roughness={0.8} />
            </mesh>
          ))}
        </group>
      ))}
      <mesh position={[0, 0.055, 0]}>
        <boxGeometry args={[0.12, 0.19, 1.18]} />
        <meshStandardMaterial color="#e0a873" roughness={0.5} />
      </mesh>
    </group>
  );
}

function GraduationCap() {
  return (
    <group position={[0.72, 0.66, 0.1]} rotation={[0.16, -0.3, -0.15]}>
      <mesh position={[0, -0.07, 0]}>
        <boxGeometry args={[0.88, 0.07, 0.64]} />
        <meshStandardMaterial color="#d3a66d" roughness={0.4} metalness={0.12} />
      </mesh>
      <mesh position={[0, 0.04, 0]}>
        <coneGeometry args={[0.34, 0.25, 4]} />
        <meshStandardMaterial color="#8979f0" roughness={0.34} metalness={0.15} />
      </mesh>
      <mesh position={[0.27, -0.08, 0.12]} rotation={[0, 0, -0.2]}>
        <cylinderGeometry args={[0.012, 0.012, 0.34, 8]} />
        <meshStandardMaterial color="#f4d18e" metalness={0.4} roughness={0.32} />
      </mesh>
      <mesh position={[0.29, -0.24, 0.12]}>
        <sphereGeometry args={[0.045, 12, 12]} />
        <meshStandardMaterial color="#f4d18e" metalness={0.35} roughness={0.3} />
      </mesh>
    </group>
  );
}

function OrbitRings({ animated = true }) {
  const ring = useRef(null);

  useFrame((state) => {
    if (!ring.current || !animated) return;
    ring.current.rotation.z = state.clock.elapsedTime * 0.14;
    ring.current.rotation.x = 0.9 + Math.sin(state.clock.elapsedTime * 0.18) * 0.08;
  });

  return (
    <group ref={ring} position={[0, 0, -0.5]}>
      <mesh>
        <torusGeometry args={[1.42, 0.012, 8, 100]} />
        <meshBasicMaterial color="#c5bfff" transparent opacity={0.55} />
      </mesh>
      <mesh rotation={[0.52, 0.24, 0.1]}>
        <torusGeometry args={[1.62, 0.008, 8, 100]} />
        <meshBasicMaterial color="#f4d197" transparent opacity={0.36} />
      </mesh>
      <mesh position={[1.42, 0, 0]}>
        <sphereGeometry args={[0.045, 16, 16]} />
        <meshStandardMaterial color="#ffe0a7" emissive="#d99b58" emissiveIntensity={0.7} />
      </mesh>
    </group>
  );
}

function Scene({ animated }) {
  return (
    <>
      <ambientLight intensity={1.7} />
      <directionalLight position={[3, 5, 4]} intensity={3.2} color="#fff1d2" />
      <pointLight position={[-3, 1, -2]} intensity={18} color="#8f84ff" />
      <Float speed={0.72} rotationIntensity={animated ? 0.07 : 0} floatIntensity={animated ? 0.08 : 0} enabled={animated}>
        <mesh position={[0, 0, -0.75]}>
          <sphereGeometry args={[0.86, 40, 40]} />
          <meshPhysicalMaterial color="#8278ee" emissive="#40378d" emissiveIntensity={0.45} roughness={0.16} metalness={0.16} transmission={0.16} thickness={0.8} clearcoat={1} clearcoatRoughness={0.12} />
        </mesh>
      </Float>
      <OrbitRings animated={animated} />
      <Float speed={1.05} rotationIntensity={animated ? 0.16 : 0} floatIntensity={animated ? 0.2 : 0} enabled={animated}>
        <OpenBook />
      </Float>
      <Float speed={1.35} rotationIntensity={animated ? 0.24 : 0} floatIntensity={animated ? 0.16 : 0} enabled={animated}>
        <GraduationCap />
      </Float>
      <Float speed={0.8} rotationIntensity={0} floatIntensity={animated ? 0.3 : 0} enabled={animated}>
        <mesh position={[-1.02, 0.7, 0.15]}>
          <icosahedronGeometry args={[0.13, 1]} />
          <meshStandardMaterial color="#f4cf90" roughness={0.32} metalness={0.24} />
        </mesh>
      </Float>
      <Float speed={1.1} rotationIntensity={0} floatIntensity={animated ? 0.22 : 0} enabled={animated}>
        <mesh position={[1.05, -0.38, -0.2]}>
          <icosahedronGeometry args={[0.095, 1]} />
          <meshStandardMaterial color="#a9a0ff" roughness={0.3} metalness={0.2} />
        </mesh>
      </Float>
      <Sparkles count={34} scale={[3.5, 2.4, 1.8]} size={2.2} speed={animated ? 0.35 : 0} opacity={0.68} color="#e8ddff" />
    </>
  );
}

function DashboardOrb() {
  const orbit = useRef(null);

  useFrame((state) => {
    if (!orbit.current) return;
    orbit.current.rotation.y = state.clock.elapsedTime * 0.22;
    orbit.current.rotation.z = Math.sin(state.clock.elapsedTime * 0.18) * 0.08;
  });

  return (
    <>
      <ambientLight intensity={1.8} />
      <pointLight position={[2, 2, 3]} intensity={18} color="#f1d2ff" />
      <pointLight position={[-2, -1, 1]} intensity={12} color="#79d8ee" />
      <Float speed={0.85} rotationIntensity={0.08} floatIntensity={0.12}>
        <mesh>
          <icosahedronGeometry args={[0.74, 3]} />
          <meshPhysicalMaterial color="#9184ff" emissive="#493dbc" emissiveIntensity={0.56} roughness={0.2} metalness={0.2} transmission={0.22} thickness={1.1} clearcoat={1} clearcoatRoughness={0.08} />
        </mesh>
      </Float>
      <group ref={orbit}>
        <mesh rotation={[0.9, 0.2, 0.25]}>
          <torusGeometry args={[1.04, 0.018, 8, 100]} />
          <meshBasicMaterial color="#d5cdff" transparent opacity={0.74} />
        </mesh>
        <mesh rotation={[0.3, 0.8, 1.15]}>
          <torusGeometry args={[1.27, 0.012, 8, 100]} />
          <meshBasicMaterial color="#f3cb8b" transparent opacity={0.7} />
        </mesh>
        <mesh position={[1.04, 0, 0]}>
          <sphereGeometry args={[0.07, 16, 16]} />
          <meshStandardMaterial color="#ffe2ad" emissive="#f1a95e" emissiveIntensity={1.2} />
        </mesh>
        <mesh position={[-1.27, 0, 0]}>
          <sphereGeometry args={[0.045, 16, 16]} />
          <meshStandardMaterial color="#b4f1ff" emissive="#79d8ee" emissiveIntensity={1} />
        </mesh>
      </group>
      <Sparkles count={22} scale={[3, 2.4, 1.5]} size={2.2} speed={0.35} opacity={0.8} color="#e5e0ff" />
    </>
  );
}

export function DashboardScene() {
  const [reducedMotion, setReducedMotion] = useState(() => (
    typeof window === "undefined" || window.matchMedia("(prefers-reduced-motion: reduce)").matches
  ));

  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updatePreference = () => setReducedMotion(preference.matches);
    preference.addEventListener("change", updatePreference);
    return () => preference.removeEventListener("change", updatePreference);
  }, []);

  return (
    <div className="dashboard-scene">
      <Canvas
        camera={{ position: [0, 0, 5], fov: 36 }}
        dpr={[1, 1.25]}
        frameloop={reducedMotion ? "demand" : "always"}
        gl={{ alpha: true, antialias: true, powerPreference: "low-power" }}
        fallback={<div className="dashboard-scene-fallback" />}
      >
        <DashboardOrb />
      </Canvas>
    </div>
  );
}

function AuthScene() {
  const [isDesktop, setIsDesktop] = useState(() => typeof window !== "undefined" && window.innerWidth > 680);
  const [reducedMotion, setReducedMotion] = useState(() => (
    typeof window === "undefined" || window.matchMedia("(prefers-reduced-motion: reduce)").matches
  ));

  useEffect(() => {
    const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updatePreferences = () => {
      setIsDesktop(window.innerWidth > 680);
      setReducedMotion(motionPreference.matches);
    };

    updatePreferences();
    window.addEventListener("resize", updatePreferences);
    motionPreference.addEventListener("change", updatePreferences);
    return () => {
      window.removeEventListener("resize", updatePreferences);
      motionPreference.removeEventListener("change", updatePreferences);
    };
  }, []);

  if (!isDesktop) return null;

  return (
    <div className="auth-scene" aria-hidden="true">
      <Canvas
        camera={{ position: [0, 1.1, 5.2], fov: 36 }}
        dpr={[1, 1.5]}
        frameloop={reducedMotion ? "demand" : "always"}
        gl={{ alpha: true, antialias: true, powerPreference: "low-power" }}
        fallback={<div className="auth-scene-fallback" />}
      >
        <Scene animated={!reducedMotion} />
      </Canvas>
    </div>
  );
}

export default AuthScene;
