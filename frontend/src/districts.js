export const MAHARASHTRA_DISTRICTS = [
  { name: "Ahmednagar", hindi: "अहमदनगर" },
  { name: "Akola", hindi: "अकोला" },
  { name: "Amravati", hindi: "अमरावती" },
  { name: "Aurangabad", hindi: "औरंगाबाद" },
  { name: "Beed", hindi: "बीड" },
  { name: "Bhandara", hindi: "भंडारा" },
  { name: "Buldhana", hindi: "बुलढाणा" },
  { name: "Chandrapur", hindi: "चंद्रपुर" },
  { name: "Dhule", hindi: "धुले" },
  { name: "Gadchiroli", hindi: "गडचिरोली" },
  { name: "Gondia", hindi: "गोंदिया" },
  { name: "Hingoli", hindi: "हिंगोली" },
  { name: "Jalgaon", hindi: "जलगांव" },
  { name: "Jalna", hindi: "जालना" },
  { name: "Kolhapur", hindi: "कोल्हापुर" },
  { name: "Latur", hindi: "लातूर" },
  { name: "Mumbai City", hindi: "मुंबई शहर" },
  { name: "Mumbai Suburban", hindi: "मुंबई उपनगर" },
  { name: "Nagpur", hindi: "नागपुर" },
  { name: "Nanded", hindi: "नांदेड" },
  { name: "Nandurbar", hindi: "नंदुरबार" },
  { name: "Nashik", hindi: "नाशिक" },
  { name: "Osmanabad", hindi: "उस्मानाबाद" },
  { name: "Palghar", hindi: "पालघर" },
  { name: "Parbhani", hindi: "परभणी" },
  { name: "Pune", hindi: "पुणे" },
  { name: "Raigad", hindi: "रायगढ़" },
  { name: "Ratnagiri", hindi: "रत्नागिरी" },
  { name: "Sangli", hindi: "सांगली" },
  { name: "Satara", hindi: "सातारा" },
  { name: "Sindhudurg", hindi: "सिंधुदुर्ग" },
  { name: "Solapur", hindi: "सोलापुर" },
  { name: "Thane", hindi: "ठाणे" },
  { name: "Wardha", hindi: "वर्धा" },
  { name: "Washim", hindi: "वाशिम" },
  { name: "Yavatmal", hindi: "यवतमाल" },
];

export function districtLabel(name, language = "en") {
  const district = MAHARASHTRA_DISTRICTS.find(
    (item) => item.name.toLowerCase() === String(name || "").toLowerCase(),
  );
  if (!district) return name;
  return language === "hi" ? `${district.name} — ${district.hindi}` : district.name;
}

export function normalizeDistrictNames(names = []) {
  return names.map((name) => {
    const district = MAHARASHTRA_DISTRICTS.find(
      (item) => item.name.toLowerCase() === String(name).trim().toLowerCase(),
    );
    return district?.name || String(name).trim();
  });
}
